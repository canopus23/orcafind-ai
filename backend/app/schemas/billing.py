from pydantic import BaseModel, Field


class RazorpayCreateOrderRequest(BaseModel):
    plan: str = Field(default="pro")
    billing: str = Field(default="monthly")  # monthly (yearly disabled for now)
    email: str = Field(default="")


class RazorpayVerifyRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class RazorpayCreateSubscriptionRequest(BaseModel):
    plan: str = Field(default="pro")
    email: str = Field(default="")


class RazorpayVerifySubscriptionRequest(BaseModel):
    razorpay_subscription_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class RazorpayChangePlanRequest(BaseModel):
    plan: str


class RazorpayCancelSubscriptionRequest(BaseModel):
    cancel_at_cycle_end: bool = Field(default=True)


class DodoCreateCheckoutSessionRequest(BaseModel):
    plan: str = Field(default="pro")
    email: str = Field(default="")
    return_url: str = Field(default="")


class DodoConfirmCheckoutRequest(BaseModel):
    subscription_id: str = Field(default="")
    payment_id: str = Field(default="")
