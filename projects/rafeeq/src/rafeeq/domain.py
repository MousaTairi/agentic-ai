from __future__ import annotations

import json
import math
import re
import secrets
import sqlite3
import time
from datetime import date, datetime, timedelta

from .schemas import Booking, Fee, Refund, Reschedule, Verify
from .storage import Store

SIM_NOW = datetime(2026, 11, 1, 9)
SIM_TODAY = SIM_NOW.date()


def working_date(start: date, days: int) -> date:
    holidays = {date(2026, 9, 23), date(2027, 2, 22)}
    while days:
        start += timedelta(days=1)
        if start.weekday() not in (4, 5) and start not in holidays:
            days -= 1
    return start


def mobile_digits(value: str) -> str:
    return re.sub(r"\D", "", value).removeprefix("00966").removeprefix("966").lstrip("0")


def verify(store: Store, sid: str, args: Verify) -> None:
    session = store.session(sid)
    if session["failures"] >= 5:
        raise PermissionError("Verification locked for this session. Contact the demo administrator.")
    with store.connect() as db:
        rows = db.execute("""SELECT a.applicant_id,a.national_id,a.mobile FROM permits p JOIN applicants a
            ON a.applicant_id=p.applicant_id OR a.agent_for=p.applicant_id WHERE p.permit_id=?""",
                          (args.permit_id,)).fetchall()
        matched = next((r for r in rows if secrets.compare_digest(r["national_id"][-4:], args.last4)
                        and secrets.compare_digest(mobile_digits(r["mobile"]), mobile_digits(args.mobile))), None)
        ok = matched is not None
        db.execute("UPDATE sessions SET verified=?,verified_until=?,failures=failures+? WHERE id=?",
                   (args.permit_id if ok else None, time.time() + 900 if ok else 0, int(not ok), sid))
        if matched is not None:
            db.execute("UPDATE sessions SET citizen_id=? WHERE id=?", (matched["applicant_id"], sid))
    if not ok:
        raise PermissionError("Verification failed. Check your details (POL-08).")


def fee(args: Fee) -> dict:
    # Match the authoritative course schedule; schemas reject negative/nonfinite inputs.
    t = args.permit_type
    if t == "BLD":
        if args.area_m2 is None:
            raise ValueError("Building fees need area_m2.")
        amount = max(500, 2 * math.ceil(args.area_m2))
    elif t == "REN":
        if args.structural and args.area_m2 is None and not args.social_security:
            raise ValueError("Structural renovation needs area_m2.")
        amount = 0 if args.social_security else 300 + (math.ceil(args.area_m2 or 0) if args.structural else 0)
    elif t == "SGN":
        if args.sign_m2 is None:
            raise ValueError("Signage fees need sign_m2.")
        amount = round(max(400, 200 * math.ceil(args.sign_m2)) * (1.25 if args.illuminated else 1))
    elif t == "FTR":
        amount = 1500
    else:
        if args.event_days is None:
            raise ValueError("Event fees need event_days.")
        amount = 1000 * args.event_days
    return {"fee_sar": amount, "policy_id": "POL-02", "permit_type": t}


def permit_info(store: Store, sid: str, permit_id: str) -> dict:
    store.authorize(sid, permit_id)
    with store.connect() as db:
        p = dict(db.execute("SELECT * FROM permits WHERE permit_id=?", (permit_id,)).fetchone())
        inspections = [dict(r) for r in db.execute(
            "SELECT inspection_id,kind,slot,status FROM inspections WHERE permit_id=?", (permit_id,))]
    details = json.loads(p["details"])
    sla = {"BLD": 15, "REN": 7, "SGN": 5, "FTR": 10, "EVT": 10}[p["type"]]
    sla += 10 if p["type"] == "SGN" and details.get("sign_m2", 0) > 12 else 0
    out = {k: p[k] for k in ("permit_id", "type", "status", "district", "fee_sar", "submitted", "decided")}
    out.update(sla_due=working_date(date.fromisoformat(p["submitted"]), sla).isoformat(),
               inspections=inspections, policy_id="POL-04")
    if p["status"] == "rejected":
        out.update(reason=p["reason"], appeal_deadline=(date.fromisoformat(p["decided"]) + timedelta(days=30)).isoformat())
    if p["status"] == "needs_info":
        out.update(info_requested=p["info_requested"],
                   info_deadline=(date.fromisoformat(p["needs_info_since"]) + timedelta(days=14)).isoformat())
    # Expose eligible refund options, not payment identifiers or account details.
    out["refund_options"] = []
    with store.connect() as db:
        for reason in ("duplicate_payment", "rejected"):
            try:
                amount = refund_amount(db, {"permit_id": permit_id, "reason": reason})
            except ValueError:
                continue
            out["refund_options"].append({"reason": reason, "amount_sar": amount,
                                          "requires_officer": amount > 1000, "policy_id": "POL-06"})
    return out


def refund_amount(db: sqlite3.Connection, args: dict) -> int:
    p = db.execute("SELECT * FROM permits WHERE permit_id=?", (args["permit_id"],)).fetchone()
    reason = args["reason"]
    paid = db.execute("SELECT amount_sar FROM payments WHERE permit_id=? ORDER BY paid_at",
                      (args["permit_id"],)).fetchall()
    if db.execute("SELECT 1 FROM refunds WHERE permit_id=?", (args["permit_id"],)).fetchone():
        raise ValueError("A refund for this permit already exists; contact an officer.")
    if not paid:
        raise ValueError("No payment is eligible for refund.")
    if reason == "duplicate_payment":
        if len(paid) < 2:
            raise ValueError("No duplicate payment found.")
        return paid[1]["amount_sar"]
    if reason == "rejected" and p["status"] == "rejected":
        return max(0, p["fee_sar"] - 100)
    # Course fixture statuses cannot prove an actual withdrawal or its stage. Fail closed.
    raise ValueError("This refund reason needs an officer to verify withdrawal history.")


def validate_booking(db: sqlite3.Connection, args: dict, reschedule: bool = False) -> dict:
    p = dict(db.execute("SELECT * FROM permits WHERE permit_id=?", (args["permit_id"],)).fetchone())
    if not ((p["status"] == "approved" and p["type"] in ("BLD", "FTR"))
            or (p["status"] == "under_review" and p["type"] in ("FTR", "EVT"))):
        raise ValueError("This permit is not eligible for an inspection (POL-05).")
    slot = datetime.fromisoformat(args["slot"])
    if slot.tzinfo is not None or slot.date() < working_date(SIM_TODAY, 2):
        raise ValueError("Use a listed Riyadh local slot at least two working days ahead.")
    canonical = slot.strftime("%Y-%m-%d %H:%M")
    if slot.second or slot.microsecond or not db.execute(
        "SELECT 1 FROM slots WHERE district=? AND slot=? AND taken=0", (p["district"], canonical)
    ).fetchone():
        raise ValueError("Slot unavailable; list slots again.")
    if reschedule:
        old = db.execute("SELECT * FROM inspections WHERE inspection_id=? AND permit_id=? AND status='booked'",
                         (args["inspection_id"], args["permit_id"])).fetchone()
        if not old or datetime.fromisoformat(old["slot"]) - SIM_NOW < timedelta(hours=24):
            raise ValueError("Rescheduling needs a booked inspection at least 24 hours away.")
        p["old_slot"] = old["slot"]
    elif db.execute("SELECT 1 FROM inspections WHERE permit_id=? AND status='booked'",
                    (args["permit_id"],)).fetchone():
        raise ValueError("A booking already exists. Reschedule it or contact an officer for another stage.")
    p["slot"] = canonical
    return p


def propose(store: Store, sid: str, tool: str, args: dict) -> dict:
    store.authorize(sid, args["permit_id"])
    payload = json.dumps(args, sort_keys=True)
    with store.connect() as db:
        db.execute("UPDATE actions SET status='expired' WHERE status='pending' AND expires<?", (time.time(),))
        if tool == "request_refund":
            amount = refund_amount(db, args)
            summary = {"amount_sar": amount, "requires_officer": amount > 1000, "policy_id": "POL-06"}
        else:
            p = validate_booking(db, args, tool == "reschedule_inspection")
            summary = {"slot": p["slot"], "district": p["district"], "policy_id": "POL-05"}
        existing = db.execute("SELECT id,status FROM actions WHERE session_id=? AND tool=? AND args=? AND status IN ('pending','awaiting_officer')",
                              (sid, tool, payload)).fetchone()
        aid = existing["id"] if existing else secrets.token_urlsafe(18)
        if not existing:
            db.execute("INSERT INTO actions VALUES (?,?,?,?,?,?,?)",
                       (aid, sid, tool, payload, "pending", time.time() + 600, json.dumps(summary)))
    return {"action_id": aid, "status": existing["status"] if existing else "pending", "summary": summary,
            "note": "Not executed. Use the confirmation card."}


def decide(store: Store, sid: str | None, aid: str, approve: bool, officer: bool = False) -> dict:
    with store.connect() as db:
        row = db.execute("SELECT * FROM actions WHERE id=?", (aid,)).fetchone()
        if not row or (not officer and row["session_id"] != sid):
            raise PermissionError("Action unavailable.")
        a = dict(row)
        expected = "awaiting_officer" if officer else "pending"
        if a["status"] != expected:
            return {"action_id": aid, "status": a["status"], "result": json.loads(a["result"] or "null")}
        if a["expires"] < time.time():
            raise ValueError("Action expired. Request a fresh proposal.")
        args = json.loads(a["args"])
        if not officer and a["tool"] != "submit_application":
            session = db.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
            if session["verified"] != args["permit_id"] or session["verified_until"] < time.time():
                raise PermissionError("Verify this application again before confirming.")
        result = None
        status = "rejected"
        if approve:
            if a["tool"] == "submit_application":
                if officer:
                    raise PermissionError("Only the applicant can submit their application.")
                from .intake import complete_application
                result = complete_application(db, sid, args)
                status = "completed"
            elif a["tool"] == "request_refund":
                amount = refund_amount(db, args)
                preview = json.loads(a["result"] or "{}")
                if preview.get("amount_sar") != amount:
                    raise ValueError("Refund amount changed. Review and confirm a fresh proposal.")
                if amount > 1000 and not officer:
                    status = "awaiting_officer"
                    result = {"amount_sar": amount, "note": "Citizen confirmed. Finance officer authorization required."}
                else:
                    rid = "REF-" + secrets.token_hex(6)
                    db.execute("INSERT INTO refunds VALUES (?,?,?,?,?,?,?)",
                               (rid, args["permit_id"], amount, args["reason"], "approved", SIM_NOW.isoformat(), "rafeeq"))
                    result = {"refund_id": rid, "amount_sar": amount, "status": "approved",
                              "note": "Synthetic approval; no money transferred."}
                    status = "completed"
            else:
                p = validate_booking(db, args, a["tool"] == "reschedule_inspection")
                if a["tool"] == "reschedule_inspection":
                    db.execute("UPDATE slots SET taken=0 WHERE district=? AND slot=?", (p["district"], p["old_slot"]))
                    iid = args["inspection_id"]
                    db.execute("UPDATE inspections SET slot=? WHERE inspection_id=?", (p["slot"], iid))
                else:
                    iid = "INS-" + secrets.token_hex(6)
                    kind = {"BLD": "foundation", "FTR": "health"}.get(p["type"], "site_visit")
                    db.execute("INSERT INTO inspections VALUES (?,?,?,?,?,?,NULL)",
                               (iid, args["permit_id"], kind, p["slot"], p["district"], "booked"))
                db.execute("UPDATE slots SET taken=1 WHERE district=? AND slot=?", (p["district"], p["slot"]))
                result = {"inspection_id": iid, "slot": p["slot"], "status": "booked"}
                status = "completed"
        db.execute("UPDATE actions SET status=?,result=?,expires=? WHERE id=?",
                   (status, json.dumps(result), time.time() + 86400 if status == "awaiting_officer" else a["expires"], aid))
        return {"action_id": aid, "status": status, "result": result}


WRITE_SCHEMAS = {"book_inspection": Booking, "reschedule_inspection": Reschedule, "request_refund": Refund}
