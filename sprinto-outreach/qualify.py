import time

import config
import llm
import scrape
import extract

FETCH_ATTEMPTS = 3   # tries per page before giving up
RETRY_WAIT = 1       # seconds before the 2nd try; doubles after each failure

PROMPT = """Sprinto sells compliance automation (SOC 2, ISO 27001, GDPR) to SaaS
companies at Series A-C that are preparing for an audit or pressed by enterprise
customers. Score this company's fit and say if more information is needed.
Return JSON: score (0-100), reason, needs_more (bool).

COMPANY: {company}"""


def fetch_with_retry(domain, path):
    """scrape.fetch returns "" on any failure, so treat empty as failed and try again."""
    wait = RETRY_WAIT
    for attempt in range(1, FETCH_ATTEMPTS + 1):
        text = scrape.fetch(domain, path)
        if text or config.OFFLINE:   # a missing cached page won't appear on retry
            return text
        if attempt < FETCH_ATTEMPTS:
            time.sleep(wait)
            wait *= 2
    return ""


def qualify(domain, company):
    result = llm.ask("qualify", domain, PROMPT.format(company=company))
    rounds = 0
    while result["needs_more"] and rounds < config.MAX_ROUNDS:
        more = fetch_with_retry(domain, "about")
        if not more:
            # still failing after retries: score on what we have, don't extract from an empty page
            result["reason"] = f"{result.get('reason', '')} (about page failed after {FETCH_ATTEMPTS} tries)".strip()
            break
        company = {**company, **extract.extract(domain, more)}
        result = llm.ask("qualify_more", domain, PROMPT.format(company=company))
        rounds += 1
    result["qualified"] = result["score"] >= config.QUALIFY_THRESHOLD
    return result
