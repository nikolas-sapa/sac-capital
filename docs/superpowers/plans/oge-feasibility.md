# OGE Executive Branch Disclosure Feasibility Report

**Status: NOT VIABLE**

## Executive Summary
The US Office of Government Ethics (OGE) does maintain public financial disclosure reports for ~1,000 Level I/II executive branch officials (including Presidents, Cabinet members, senior White House staff, and Designated Agency Ethics Officials). However, **the system is designed as a document request service, not a machine-readable data API**. This makes it unsuitable for automated, real-time transaction data collection.

## Probe Results

### 1. Accessible Endpoints

| Endpoint | Status | Purpose |
|----------|--------|---------|
| `https://extapps2.oge.gov/201/Presiden.nsf/` | 200 ✓ | Presidential Nominee & Appointee Request System (main portal) |
| `https://extapps2.oge.gov/201/Presiden.nsf/dlgDocumentListnew?OpenForm&ln=[LastName]` | 200 ✓ | Document request form for individual by last name |
| `https://www.oge.gov/web/OGE.nsf/Officials%20Individual%20Disclosures%20Search%20Collection` | 200 ✓ | Main disclosure search interface (Lotus Domino form) |
| `https://extapps2.oge.gov/api/` | 200 | Generic Zimbra/Domino app API (not OGE-specific) |

### 2. Data Availability

**Confirmed documents exist for:**
- Donald Trump (Presidential Candidate, President)
- JD Vance (Vice President)
- Marco Rubio (Secretary of State equivalent)
- Other cabinet/Level I officials

**Form types available:**
- **Form 278e**: Annual holdings snapshot (low signal — published once/year)
- **Form 278-T**: Periodic Transaction Reports (high signal — transaction dates and amounts)

### 3. Critical Limitation: No Structured Data Access

**What we expected to find:**
- JSON/CSV/XML endpoints listing transactions
- Direct downloadable reports with structured data
- Search results with filtering by date, ticker, or transaction type

**What actually exists:**
- A **document request form** with HTML radio buttons for selecting individuals
- Email-based fulfillment process (201forms@oge.gov)
- 2 business day turnaround
- Manual PDF/document delivery (no API calls)

### 4. Why This Is Not Viable

1. **No Real-Time Data**: Must email to request documents → 2-day wait
2. **No Automation**: Requires human interaction; no REST/GraphQL endpoints
3. **No Batch Access**: Max 5 documents per request
4. **Unstructured Format**: Documents delivered as PDFs, not structured data
5. **No Transaction List**: No way to search or filter transactions without requesting the PDF first
6. **No Freshness Metadata**: Cannot determine filing dates or transaction dates without requesting the document

### 5. Architecture Differences from House/Senate STOCK Act

**Why House STOCK Act works** (already in `politician_disclosures.py`):
- Public JSON mirrors maintained by third parties: S3 URLs for all transactions as JSON arrays
- House Clerk provides ZIP files with XML indices + PTR PDFs
- Both have structured, downloadable data without requesting via email

**Why OGE executive branch does NOT work**:
- OGE maintains an internal document database
- Access is via email request, not HTTP data endpoints
- No public JSON/CSV mirrors exist (checked GitHub)
- No batch download capability
- No way to build a feed of recent transactions

## URLs Attempted (for reference)

```
✗ https://data.oge.gov/                                    (DNS fail)
✗ https://api.oge.gov/                                     (DNS fail)
✗ https://disclosures.oge.gov/                             (DNS fail)
✗ https://www.oge.gov/web/OGE.nsf/alldocuments             (404)
✗ https://extapps2.oge.gov/api/disclosures                 (404)
✗ https://extapps2.oge.gov/api/search                      (404)
✗ https://www.oge.gov/web/OGE.nsf?OpenView&count=100       (400)
✓ https://extapps2.oge.gov/201/Presiden.nsf/               (200 — request portal)
✓ https://extapps2.oge.gov/201/Presiden.nsf/dlgDocumentListnew?OpenForm&ln=Trump (200 — form)
```

## Recommendation

**Do NOT build OGEDisclosureProvider.** The OGE system requires email requests and manual document handling.

### Alternatives to Consider
1. **Wait for third-party mirrors**: Some researcher/data org may eventually mirror OGE data as they have for House/Senate. Monitor GitHub for `oge+disclosure` repos.
2. **FOIA requests**: Bulk request all Form 278-T filings for the current administration (2025+), but this will take weeks/months and is not real-time.
3. **Paid data services**: Bloomberg, Reuters, or specialized gov-data vendors may license OGE data in structured format.
4. **Manual updates**: Subscribe to OGE email updates for specific officials and manually parse PDFs (not scalable).

## Files Examined
- `/private/tmp/claude-503/.../scratchpad/oge_form.html` — Presidential Nominee portal main page
- `/private/tmp/claude-503/.../scratchpad/oge_trump_docs.html` — Document request form for Trump

---

**Probe completed:** 2025-06-30  
**Conclusion:** OGE executive branch disclosures are NOT machine-fetchable in real-time.
