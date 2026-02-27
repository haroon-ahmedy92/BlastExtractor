from pydantic import BaseModel, HttpUrl


class JobListing(BaseModel):
    title: str
    url: HttpUrl
    source: str
