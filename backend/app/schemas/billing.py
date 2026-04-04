from pydantic import BaseModel, Field


class RazorpayCreateOrderRequest(BaseModel):
    plan: str = Field(default="pro")
    billing: str = Field(default="monthly")  # monthly | yearly
    email: str = Field(default="")


class RazorpayVerifyRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str

