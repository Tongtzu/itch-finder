from itch_finder.cluster import cluster
from itch_finder.models import Post
from itch_finder.offers import build_stack, sales_needed
from itch_finder.signals import score_post


def scored(title, body=""):
    return score_post(Post(source="t", post_id=title, title=title, body=body,
                           url="u", comments=0, upvotes=0, created_utc=0))


def test_cluster_groups_shared_keyword():
    posts = [scored("Frustrated with invoice reconciliation"),
             scored("Invoice matching is a nightmare"),
             scored("Struggling to reconcile invoice totals"),
             scored("Frustrated with pivot tables refreshing")]
    clusters = cluster(posts, top_n=3)
    top = clusters[0]
    assert top.keyword == "invoice"
    assert len(top.posts) == 3


def test_cluster_empty_input():
    assert cluster([], top_n=5) == []


def test_build_stack_has_three_ascending_tiers():
    clusters = cluster([scored("Frustrated with invoice reconciliation"),
                        scored("Invoice matching is a nightmare")], top_n=1)
    stack = build_stack(clusters[0], niche="excel")
    prices = [o.price for o in stack]
    assert len(stack) == 3
    assert prices == sorted(prices)
    assert all("invoice" in o.name.lower() for o in stack)


def test_sales_needed_rounds_up():
    assert sales_needed(400, 197) == 3
    assert sales_needed(400, 19) == 22
    assert sales_needed(0, 19) == 0


def test_cluster_labels_with_shared_phrase():
    posts = [scored("Pivot table refresh is frustrating"),
             scored("Struggling with pivot table refresh again"),
             scored("Pivot table totals wrong, frustrated")]
    top = cluster(posts, top_n=3)[0]
    assert top.keyword == "pivot table"
    assert len(top.posts) == 3


def test_cluster_drops_terms_seen_in_only_one_post():
    posts = [scored("Frustrated with invoice reconciliation"),
             scored("Struggling with payroll exports")]
    assert cluster(posts, top_n=5) == []


def test_cluster_skips_terms_overlapping_a_chosen_label():
    posts = [scored("Pivot table refresh is frustrating"),
             scored("Struggling with pivot table refresh again")]
    labels = [c.keyword for c in cluster(posts, top_n=5)]
    assert labels.count("pivot table") + labels.count("pivot") + labels.count("table") == 1


def test_cluster_ignores_filler_words():
    posts = [scored("Frustrated, figured out part of it as well"),
             scored("Struggling, worked out part of it as well")]
    assert cluster(posts, top_n=5) == []


def test_cluster_drops_groups_left_with_one_post():
    posts = [scored("Pivot table refresh is frustrating"),
             scored("Struggling with pivot table refresh"),
             scored("Refresh macro is frustrating")]
    assert [c.keyword for c in cluster(posts, top_n=5)] == ["pivot table"]
