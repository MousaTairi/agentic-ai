"""Conservative municipal routing before provider calls; no general-purpose assistant mode."""
import re

MUNICIPAL = re.compile(
    r"permit|municipal|application|inspection|appointment|schedule|status|refund|appeal|renovat|food.?truck|signage|building|fee|"
    r"register|registration|sign.up|account|document|\b(?:BLD|REN|SGN|FTR|EVT)\b|"
    r"تصريح|تصاريح|رخص|بلدي|فحص|تفتيش|استرداد|اعتراض|ترميم|عرب[ةات]+|لوح|بناء|رسوم|"
    r"تسجيل|سجلني|حساب|مستند|طلب|حجز|موعد|تحقق", re.I)
UNRELATED = re.compile(
    r"(?:write|generate|give|debug).*\bcode\b|\b(?:python|javascript|typescript|java|c\+\+)\b|"
    r"sort(?:ing)?.*(?:list|array)|\b(?:weather|football|recipe|horoscope|poem|president)\b|"
    r"اكتب.*(?:كود|قصيدة|شعر)|ترتيب.*قائم|طقس|كرة القدم|وصفة طبخ", re.I)


def supported(message: str, has_context: bool) -> bool:
    if UNRELATED.search(message):
        return False
    if MUNICIPAL.search(message):
        return True
    if re.fullmatch(r"\s*(?:hi|hello|hey|thanks|thank you|مرحبا|مرحبًا|السلام عليكم|شكرا|شكرًا)[!.؟?\s]*", message, re.I):
        return True
    # Short follow-ups are useful only within an existing municipal conversation.
    return has_context and bool(re.search(
        r"^\s*(?:yes|no|the first|the second|next|continue|what about|what information|what do you need|that one|morning|afternoon|"
        r"monday|tuesday|wednesday|thursday|sunday|al-|\d|نعم|لا\b|الأول|الثاني|التالي|تابع|أكمل|الصباح|المساء|الأحد|الاثنين|الثلاثاء|الأربعاء|الخميس)",
        message, re.I))


def intent(message: str) -> str:
    if (not re.search(r"^\s*(?:what\b|how\b|when\b|can\b|could\b|ما\s|هل\s|متى\s|كيف\s)", message, re.I)
            and re.search(r"\bI (?:want|need|would like)[^?.!]*refund|\b(?:propose|prepare|request)[^?.!]*refund|"
                          r"(?:أريد|اريد|أود|اود|اقترح|جهّ?ز|قدّ?م)[^؟.!]*(?:استرداد|استرجاع)", message, re.I)):
        return "refund"
    if re.search(r"register|sign.up|create.*account|تسجيل|سجلني|إنشاء حساب|انشاء حساب", message, re.I):
        return "register"
    if (re.search(r"status|deadline|حالة|موعد.*اعتراض", message, re.I)
            and not re.search(r"book|reserv|حجز|احجز|أحجز|فحص|تفتيش", message, re.I)):
        return "policy"
    if re.search(r"(?:apply|submit|get|obtain|continue).*(?:permit|application)|(?:أحصل|احصل|تقديم|أقدم|اقدم).*(?:رخص|تصريح|طلب)", message, re.I):
        return "apply"
    if re.search(r"book|reserv|reschedul|حجز|احجز|أحجز|(?:موعد|جدول).*(?:فحص|تفتيش)|(?:فحص|تفتيش).*موعد", message, re.I):
        return "book"
    return "policy"
