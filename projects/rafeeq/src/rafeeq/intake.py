"""Local synthetic citizen intake. Identity values never enter model messages."""
from __future__ import annotations

import json
import secrets
import time

from .domain import SIM_NOW, fee, mobile_digits
from .schemas import Application, Register
from .storage import Store

DOCUMENTS = {
    "BLD": ["title_deed", "engineering_drawings", "site_plan", "contractor_contract"],
    "REN": ["title_deed", "works_description", "photos"],
    "SGN": ["commercial_registration", "lease_or_title", "sign_design"],
    "FTR": ["vehicle_registration", "worker_health_certificates", "passed_health_inspection"],
    "EVT": ["site_plan", "safety_plan"],
}


def register(store: Store, sid: str, args: Register) -> dict:
    store.session(sid)
    with store.connect() as db:
        existing = db.execute("SELECT citizen_id FROM sessions WHERE id=?", (sid,)).fetchone()[0]
        if existing:
            return {"ok": True, "registered": True}
        # Avoid creating a second identity for an existing applicant; use verification instead.
        if any(mobile_digits(row["mobile"] or "") == mobile_digits(args.mobile)
               for row in db.execute("SELECT mobile FROM applicants")):
            raise ValueError("Use application verification for an existing applicant, or use new synthetic demo details.")
        citizen = "DEMO-" + secrets.token_hex(8)
        db.execute("INSERT INTO applicants VALUES (?,?,?,?,?,?,?,?,NULL)",
                   (citizen, args.display_name, args.display_name, "DEMO-" + args.last4, args.mobile,
                    None, None, 0))
        db.execute("UPDATE sessions SET citizen_id=? WHERE id=?", (citizen, sid))
    return {"ok": True, "registered": True, "note": "Synthetic demo profile created; no real government account."}


def my_applications(store: Store, sid: str) -> dict:
    session = store.session(sid)
    with store.connect() as db:
        rows = [dict(r) for r in db.execute(
            "SELECT permit_id,type,status,district FROM permits WHERE applicant_id=? ORDER BY submitted DESC,rowid DESC LIMIT 10",
            (session["citizen_id"],))] if session["citizen_id"] and session["verified_until"] > time.time() else []
    return {"registered": bool(session["citizen_id"]), "applications": rows,
            "verified_application": session["verified"] if session["verified_until"] > time.time() else None}


def application_options() -> dict:
    return {"documents": DOCUMENTS,
            "districts": ["Al-Shati", "Al-Jamiah", "Al-Rawdah", "Al-Olaya", "Al-Nakheel", "Al-Malqa"]}


def quote(args: Application) -> dict:
    if args.permit_type == "REN" and args.social_security:
        raise ValueError("An officer must verify the primary-residence exemption before a zero-fee application.")
    required = list(DOCUMENTS[args.permit_type])
    if args.permit_type == "REN" and args.structural:
        required.append("structural_report")
    if args.permit_type == "SGN" and args.illuminated:
        required.append("electrical_certificate")
    if args.permit_type == "EVT":
        if args.attendees is None:
            raise ValueError("Provide the expected attendee count for an event application.")
        if args.attendees > 500:
            required.append("civil_defense_review")
    allowed = (set(required) | ({"structural_report"} if args.permit_type == "REN" else set())
               | ({"electrical_certificate"} if args.permit_type == "SGN" else set())
               | ({"civil_defense_review"} if args.permit_type == "EVT" else set()))
    if set(args.documents) - allowed:
        raise ValueError("Unrecognized document declaration for this permit type.")
    return {**fee(args), "missing_documents": sorted(set(required) - set(args.documents)),
            "documents_are_declarations": True, "payment_is_simulated": True}


def propose_application(store: Store, sid: str, args: Application) -> dict:
    session = store.session(sid)
    if not session["citizen_id"]:
        raise PermissionError("Create your synthetic profile in the registration card first.")
    summary = quote(args)
    payload = json.dumps(args.model_dump(mode="json"), sort_keys=True)
    with store.connect() as db:
        row = db.execute("SELECT id FROM actions WHERE session_id=? AND tool='submit_application' AND args=?"
                         " AND status='pending' AND expires>?", (sid, payload, time.time())).fetchone()
        aid = row["id"] if row else secrets.token_urlsafe(18)
        if not row:
            db.execute("UPDATE actions SET status='expired' WHERE session_id=? AND tool='submit_application'"
                       " AND status='pending' AND expires<?", (sid, time.time()))
            db.execute("INSERT INTO actions VALUES (?,?,?,?,?,?,?)",
                       (aid, sid, "submit_application", payload, "pending", time.time()+600, json.dumps(summary)))
    return {"action_id": aid, "status": "pending", "summary": summary,
            "note": "Review fee and missing documents. Confirm to submit with simulated payment; no permit approval."}


def complete_application(db, sid: str, args: dict) -> dict:
    session = db.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
    if not session or not session["citizen_id"] or session["expires"] < time.time():
        raise PermissionError("Registration session expired.")
    parsed = Application.model_validate_json(json.dumps(args))
    summary = quote(parsed)
    for _ in range(100):
        pid = parsed.permit_type + "-" + str(10000 + secrets.randbelow(90000))
        if not db.execute("SELECT 1 FROM permits WHERE permit_id=?", (pid,)).fetchone():
            break
    else:
        raise ValueError("Could not allocate an application reference. Try again.")
    missing = summary["missing_documents"]
    status = "needs_info" if missing else "submitted"
    db.execute("INSERT INTO permits VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL)",
               (pid, session["citizen_id"], parsed.permit_type, status, parsed.district,
                json.dumps(args), summary["fee_sar"], SIM_NOW.date().isoformat(), None,
                SIM_NOW.date().isoformat() if missing else None, ", ".join(missing) if missing else None))
    # Explicitly labelled simulated payment; no external payment tool or real charge.
    db.execute("INSERT INTO payments VALUES (?,?,?,?,?)",
               ("DEMO-PAY-" + secrets.token_hex(8), pid, summary["fee_sar"], SIM_NOW.isoformat(), "simulated"))
    db.execute("UPDATE sessions SET verified=?,verified_until=? WHERE id=?", (pid, time.time()+900, sid))
    return {"permit_id": pid, "status": status, **summary,
            "note": "Application received, not approved. Document declarations need officer validation."}


def begin_review(store: Store, permit_id: str) -> dict:
    # Invoked only by the separate authenticated licensing-reviewer endpoint, never an agent tool.
    with store.connect() as db:
        p = db.execute("SELECT * FROM permits WHERE permit_id=?", (permit_id,)).fetchone()
        if not p or p["status"] not in ("submitted", "needs_info", "under_review"):
            raise ValueError("Application cannot enter review from its current state.")
        db.execute("UPDATE permits SET status='under_review' WHERE permit_id=?", (permit_id,))
    return {"permit_id": permit_id, "status": "under_review",
            "note": "Officer took the application into review. This is not permit approval."}
