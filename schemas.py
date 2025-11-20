"""
Application Database Schemas

Each Pydantic model corresponds to a MongoDB collection with the
collection name equal to the lowercase of the class name.

Use these models for request/response validation.
"""
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, EmailStr

# -------------------- Core Domain Schemas --------------------

class ProposalInput(BaseModel):
    title: str = Field(..., description="Event or program title")
    description: str = Field(..., description="Overview and goals")
    date: Optional[str] = Field(None, description="Date or date range")
    location: Optional[str] = Field(None, description="Event location or service region")
    audience_size: Optional[int] = Field(None, ge=0)
    demographics: Optional[str] = Field(None, description="Audience demographics summary")
    engagement_channels: Optional[List[str]] = Field(default_factory=list, description="Channels: email, social, on-site, etc.")
    objectives: Optional[List[str]] = Field(default_factory=list)
    industries_target: Optional[List[str]] = Field(default_factory=list, description="Industries to prioritize for sponsors")

class BenefitTier(BaseModel):
    name: str
    price: float
    benefits: List[str]

class Proposal(BaseModel):
    title: str
    description: str
    date: Optional[str] = None
    location: Optional[str] = None
    audience_summary: str
    value_proposition: List[str]
    tiers: List[BenefitTier]
    objectives: List[str] = Field(default_factory=list)

class Sponsor(BaseModel):
    name: str
    industry: str
    location: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    status: Literal[
        'new',
        'contacted',
        'in_discussion',
        'pending',
        'confirmed',
        'declined'
    ] = 'new'
    proposal_id: Optional[str] = Field(None, description="Related proposal id if applicable")
    notes: Optional[str] = None
    next_follow_up: Optional[str] = Field(None, description="ISO date string for next follow-up")

class Interaction(BaseModel):
    sponsor_id: str
    type: Literal['email', 'call', 'meeting', 'note'] = 'note'
    content: str

class FollowUp(BaseModel):
    sponsor_id: str
    due_date: str
    note: Optional[str] = None

# -------------------- Auxiliary Schemas (Requests) --------------------

class FindSponsorsRequest(BaseModel):
    location: str
    industries: List[str] = Field(default_factory=list)
    limit: int = 10

class GenerateEmailRequest(BaseModel):
    sponsor_id: str
    proposal_id: Optional[str] = None
    tone: Literal['professional', 'friendly', 'concise'] = 'professional'

class UpdateStatusRequest(BaseModel):
    sponsor_id: str
    status: Sponsor.model_fields['status'].annotation  # reuse literal

class AddNoteRequest(BaseModel):
    sponsor_id: str
    note: str

class LogInteractionRequest(BaseModel):
    sponsor_id: str
    type: Interaction.model_fields['type'].annotation
    content: str

class ScheduleFollowUpRequest(BaseModel):
    sponsor_id: str
    due_date: str
    note: Optional[str] = None

# The Flames database viewer can introspect these models via /schema
