import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from typing import List
from io import BytesIO
from datetime import datetime

from database import db, create_document, get_documents
from schemas import (
    ProposalInput, Proposal, BenefitTier,
    Sponsor,
    FindSponsorsRequest, GenerateEmailRequest,
    UpdateStatusRequest, AddNoteRequest,
    LogInteractionRequest, ScheduleFollowUpRequest
)

app = FastAPI(title="Sponsorship Manager API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------- Utility generators --------------------

def synthesize_audience_summary(inp: ProposalInput) -> str:
    size = f"~{inp.audience_size:,} attendees" if inp.audience_size else "audience aligned to your niche"
    demo = inp.demographics or "Mixed age groups with strong local presence"
    channels = ", ".join(inp.engagement_channels) if inp.engagement_channels else "email, social, on-site activations"
    return f"Projected reach {size}. Demographics: {demo}. Engagement via {channels}."

def default_tiers(inp: ProposalInput) -> List[BenefitTier]:
    base_price = max(500, (inp.audience_size or 500) * 0.5)
    return [
        BenefitTier(name="Bronze", price=round(base_price, 2), benefits=[
            "Logo on website", "Social media mention", "2 event passes"
        ]),
        BenefitTier(name="Silver", price=round(base_price * 2, 2), benefits=[
            "Medium logo placement", "2 dedicated social posts", "4 event passes", "Booth space"
        ]),
        BenefitTier(name="Gold", price=round(base_price * 3.5, 2), benefits=[
            "Prime logo placement", "Newsletter feature", "Stage shoutout", "6 event passes", "Lead capture access"
        ]),
    ]

def value_points(inp: ProposalInput) -> List[str]:
    return [
        "Direct access to target local audiences",
        "Brand visibility across digital and on-site touchpoints",
        "Measurable engagement and post-event reporting",
        "Long-term partnership opportunities",
    ]

# -------------------- Proposal Builder --------------------

@app.post("/api/proposals/generate", response_model=Proposal)
def generate_proposal(inp: ProposalInput):
    proposal = Proposal(
        title=inp.title,
        description=inp.description,
        date=inp.date,
        location=inp.location,
        audience_summary=synthesize_audience_summary(inp),
        value_proposition=value_points(inp),
        tiers=default_tiers(inp),
        objectives=inp.objectives or [],
    )
    # Persist snapshot for tracking
    create_document("proposal", proposal.model_dump())
    return proposal

@app.post("/api/proposals/export/pdf")
def export_proposal_pdf(inp: ProposalInput):
    # Lazy import to avoid hard dependency on startup
    from reportlab.lib.pagesizes import LETTER
    from reportlab.pdfgen import canvas

    proposal = Proposal(
        title=inp.title,
        description=inp.description,
        date=inp.date,
        location=inp.location,
        audience_summary=synthesize_audience_summary(inp),
        value_proposition=value_points(inp),
        tiers=default_tiers(inp),
        objectives=inp.objectives or [],
    )

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=LETTER)
    width, height = LETTER
    y = height - 50

    def write(text, size=12, leading=16):
        nonlocal y
        c.setFont("Helvetica", size)
        for line in text.split("\n"):
            c.drawString(50, y, line)
            y -= leading

    write(proposal.title, size=18, leading=22)
    write(proposal.description)
    write(f"Date: {proposal.date or 'TBD'}")
    write(f"Location: {proposal.location or 'TBD'}")
    write(" ")
    write("Audience Summary:")
    write(proposal.audience_summary)
    write(" ")
    write("Value Proposition:")
    for vp in proposal.value_proposition:
        write(f"- {vp}")
    write(" ")
    write("Tiers:")
    for tier in proposal.tiers:
        write(f"{tier.name} - ${tier.price:,.2f}")
        for b in tier.benefits:
            write(f"  • {b}")
        write(" ")

    c.showPage()
    c.save()
    buffer.seek(0)

    return StreamingResponse(buffer, media_type="application/pdf", headers={
        "Content-Disposition": f"attachment; filename=proposal_{proposal.title.replace(' ', '_')}.pdf"
    })

# -------------------- Local Sponsor Finder --------------------

SEED_BUSINESSES = [
    {"name": "City Fitness", "industry": "Health & Wellness", "website": "https://cityfitness.example"},
    {"name": "Brewed Awakenings", "industry": "Food & Beverage", "website": "https://brew.example"},
    {"name": "Green Wheels Bikes", "industry": "Retail", "website": "https://greenwheels.example"},
    {"name": "Tech Hub Co-Work", "industry": "Technology", "website": "https://techhub.example"},
    {"name": "River Bank Credit", "industry": "Finance", "website": "https://riverbank.example"},
]

@app.post("/api/sponsors/find", response_model=List[Sponsor])
def find_sponsors(req: FindSponsorsRequest):
    matches = []
    for b in SEED_BUSINESSES:
        if not req.industries or any(i.lower() in b["industry"].lower() for i in req.industries):
            matches.append(Sponsor(
                name=b["name"],
                industry=b["industry"],
                location=req.location,
                email=f"info@{b['name'].replace(' ', '').lower()}.com",
                phone="(555) 123-4567",
                website=b["website"],
            ))
    return matches[: req.limit]

# -------------------- Tracking & CRM --------------------

@app.post("/api/sponsors/create")
def create_sponsor(sponsor: Sponsor):
    sponsor_id = create_document("sponsor", sponsor.model_dump())
    return {"id": sponsor_id}

@app.get("/api/sponsors")
def list_sponsors(status: str | None = None):
    filt = {"status": status} if status else {}
    docs = get_documents("sponsor", filt, limit=100)
    for d in docs:
        d["_id"] = str(d["_id"])  # jsonify
    return docs

@app.post("/api/sponsors/status")
def update_status(req: UpdateStatusRequest):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    from bson import ObjectId
    try:
        oid = ObjectId(req.sponsor_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid sponsor id")
    db["sponsor"].update_one({"_id": oid}, {"$set": {"status": req.status, "updated_at": datetime.utcnow()}})
    return {"ok": True}

@app.post("/api/sponsors/note")
def add_note(req: AddNoteRequest):
    from bson import ObjectId
    try:
        oid = ObjectId(req.sponsor_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid sponsor id")
    db["sponsor"].update_one({"_id": oid}, {"$set": {"notes": req.note, "updated_at": datetime.utcnow()}})
    return {"ok": True}

@app.post("/api/sponsors/interaction")
def log_interaction(req: LogInteractionRequest):
    _id = create_document("interaction", req.model_dump())
    return {"id": _id}

@app.post("/api/sponsors/followup")
def schedule_followup(req: ScheduleFollowUpRequest):
    _id = create_document("followup", req.model_dump())
    return {"id": _id}

@app.get("/api/dashboard")
def dashboard_overview():
    statuses = ["new", "contacted", "in_discussion", "pending", "confirmed", "declined"]
    overview = {}
    for s in statuses:
        overview[s] = db["sponsor"].count_documents({"status": s}) if db else 0
    upcoming = list(db["followup"].find({}).sort("due_date", 1).limit(5)) if db else []
    for u in upcoming:
        u["_id"] = str(u["_id"]) if "_id" in u else None
    return {"counts": overview, "upcoming_followups": upcoming}

# -------------------- Outreach Tools --------------------

@app.post("/api/outreach/email")
def generate_outreach_email(req: GenerateEmailRequest):
    from bson import ObjectId
    sponsor = None
    if db and req.sponsor_id:
        try:
            sponsor = db["sponsor"].find_one({"_id": ObjectId(req.sponsor_id)})
        except Exception:
            sponsor = None
    company = sponsor.get("name") if sponsor else "Partner"
    subject = f"Sponsorship Opportunity: {company} x Our Event"
    body = (
        "Hello "
        + (company if company != "Partner" else "there")
        + ",\n\n"
        + "I'm reaching out to explore a potential sponsorship partnership. Based on your focus in "
        + (sponsor.get("industry") if sponsor else "your industry")
        + ", we believe there's strong alignment with our audience.\n\n"
        + "Happy to send a tailored proposal and discuss options (Bronze, Silver, Gold) suited to your goals.\n\n"
        + "Best regards,\nYour Name"
    )
    return {"subject": subject, "body": body}

# -------------------- Health --------------------

@app.get("/")
def read_root():
    return {"message": "Sponsorship Manager API running"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = os.getenv("DATABASE_NAME") or "Unknown"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    return response

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
