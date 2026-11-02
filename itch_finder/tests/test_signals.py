from itch_finder.models import Post
from itch_finder.signals import score_post, qualifying


def make_post(title, body="", comments=0, upvotes=0):
    return Post(source="test", post_id=title[:8], title=title, body=body,
                url="https://example.com", comments=comments, upvotes=upvotes,
                created_utc=0)


def test_neutral_post_has_no_pain():
    scored = score_post(make_post("Show off my new desk setup"))
    assert scored.pain == 0
    assert scored.total == 0


def test_tool_request_counts_as_pain():
    scored = score_post(make_post("Is there a tool to merge 40 invoices into one sheet?"))
    assert scored.pain >= 3


def test_money_signal_outweighs_plain_pain():
    plain = score_post(make_post("Struggling with VLOOKUP across workbooks"))
    paid = score_post(make_post("Struggling with VLOOKUP across workbooks",
                                "I would pay someone to fix this, losing clients"))
    assert paid.total > plain.total
    assert paid.money > 0
    assert paid.urgency > 0


def test_engagement_adds_bonus_only_when_pain_exists():
    quiet = score_post(make_post("Frustrated with payroll exports", comments=0))
    loud = score_post(make_post("Frustrated with payroll exports", comments=50))
    neutral_loud = score_post(make_post("Look at my cat", comments=500))
    assert loud.total > quiet.total
    assert neutral_loud.total == 0


def test_scoring_does_not_mutate_post():
    post = make_post("I hate manually copying data every day")
    score_post(post)
    assert post.title == "I hate manually copying data every day"


def test_qualifying_filters_and_sorts():
    posts = [make_post("nice weather"),
             make_post("is there an app for this? I'd happily pay, urgent"),
             make_post("frustrating export bug")]
    result = qualifying(posts, min_score=1)
    assert len(result) == 2
    assert result[0].total >= result[1].total
