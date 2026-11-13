from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ContactMessage(BaseModel):
    project: str = Field(min_length=1, max_length=80)
    subject: str = Field(min_length=1, max_length=160)
    message: str = Field(min_length=1, max_length=3500)
    urgency: Literal["low", "normal", "high"] = "normal"

    @field_validator("project", "subject", "message")
    @classmethod
    def clean_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Le texte ne peut pas être vide.")
        return cleaned

    @field_validator("project", "subject")
    @classmethod
    def prevent_header_injection(cls, value: str) -> str:
        if "\r" in value or "\n" in value:
            raise ValueError("Les retours à la ligne sont interdits dans ce champ.")
        return value

    def formatted_body(self) -> str:
        return (
            f"Projet : {self.project}\n"
            f"Urgence : {self.urgency}\n"
            f"Sujet : {self.subject}\n\n"
            f"{self.message}"
        )
