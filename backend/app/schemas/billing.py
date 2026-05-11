from pydantic import BaseModel, Field


class ChangePlanRequest(BaseModel):
    plan: str


class CancelSubscriptionRequest(BaseModel):
    cancel_at_cycle_end: bool = Field(default=True)


class RazorpayCreateOrderRequest(BaseModel):
    plan: str = Field(default="pro")
    email: str = Field(default="")
    return_url: str = Field(default="")


class RazorpayChangePlanRequest(ChangePlanRequest):
    pass


class DodoCreateCheckoutSessionRequest(BaseModel):
    plan: str = Field(default="pro")
    email: str = Field(default="")
    return_url: str = Field(default="")


class DodoConfirmCheckoutRequest(BaseModel):
    subscription_id: str = Field(default="")
    payment_id: str = Field(default="")
