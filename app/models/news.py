from pydantic import BaseModel


class NewsModel(BaseModel):
    title: str
    summary: str
    source: str
    link: str
    published: str