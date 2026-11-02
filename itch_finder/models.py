"""Immutable data types shared across the pain miner pipeline."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Post:
    source: str
    post_id: str
    title: str
    body: str
    url: str
    comments: int
    upvotes: int
    created_utc: float

    @property
    def text(self) -> str:
        return f"{self.title}\n{self.body}"


@dataclass(frozen=True)
class ScoredPost:
    post: Post
    pain: int
    money: int
    urgency: int
    total: float


@dataclass(frozen=True)
class Cluster:
    keyword: str
    posts: tuple[ScoredPost, ...]

    @property
    def score(self) -> float:
        return round(sum(p.total for p in self.posts), 2)

    @property
    def money_hits(self) -> int:
        return sum(1 for p in self.posts if p.money > 0)


@dataclass(frozen=True)
class Offer:
    tier: str
    name: str
    price: int
    deliverable: str
    build_time: str
    pitch: str
