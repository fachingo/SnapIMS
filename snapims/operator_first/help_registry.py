from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Iterable

@dataclass(frozen=True, slots=True)
class HelpTopic:
    key: str
    title: str
    purpose: str
    when_to_use: str
    effect: str
    warnings: str = ""
    example: str = ""
    related: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()

TOPICS = {
    topic.key: topic for topic in (
        HelpTopic("global.search","Item Search","Search SnapIMS by canonical/exact title and inspect what the system knows across local inventory, pricing, Shopify sync, and metadata.","Use whenever you want to find copies or history without knowing which database owns it.","Opens unified title intelligence. Search is informational and never forces a workflow decision.","Ambiguous titles stay separate.","Search The Shining to see local copies, batches, prices, and current Shopify links.",keywords=("search","inventory","title")),
        HelpTopic("global.command_palette","Ctrl+K command palette","Find navigation, items, settings, commands, and help from anywhere.","Use instead of hunting through menus.","Opens the global palette and focuses its search field.",keywords=("ctrl+k","commands","navigation")),
        HelpTopic("review.title","Recognition title","The operator-approved title for the tape.","Verify the recognition suggestion or type a correction.","Enter approves the current title/tags and advances. Blank is allowed but remains flagged.","Enter never opens Edit Details.","The Shining",related=("review.approve","review.edit_details"),keywords=("title","recognition","approve")),
        HelpTopic("review.tags","Approved tags","Zero to three conservative automatic tags from the closed vocabulary; operator edits are authoritative.","Review tags during Recognition Review.","Saved tags become searchable and Shopify-visible according to tag definitions.","Years are never automatic tags; fewer relevant tags are better than filler.","horror, psychological horror",related=("review.approve",),keywords=("tags","genre","actor","franchise")),
        HelpTopic("review.approve","Approve & Next","Accept the current title/tag review and move to the next item.","Use when the recognition is sufficiently correct.","Marks operator review without requiring price, barcode, location, or metadata completeness.","Approval does not mean publish-ready.",related=("review.title","review.tags"),keywords=("enter","approve","next")),
        HelpTopic("review.reject","Reject","Reject the current recognition result and continue.","Use when the recognition suggestion is wrong enough that it should not be accepted.","Marks the recognition attempt rejected/attention-needed and advances without forcing Edit Details.",keywords=("reject","bad recognition")),
        HelpTopic("review.skip","Skip","Defer this item and continue.","Use when you intentionally do not want to decide now.","Preserves current state and advances; the item remains available for later review.",keywords=("skip","later","defer")),
        HelpTopic("review.edit_details","Edit Details","Open the full exception editor.","Use only when you intentionally need fields beyond title/tags.","Exposes existing advanced item fields without changing the normal Recognition Review workflow.","SnapIMS must never open this automatically.",keywords=("exception editor","advanced")),
        HelpTopic("review.bulk_confidence","Approve all at or above confidence","Bulk-approve eligible recognized items above an operator-selected confidence threshold.","Use after scanning batch recognition quality.","Shows a count/confirmation first, excludes failed/blank/rejected/below-threshold items by default.",keywords=("confidence","bulk approve")),
        HelpTopic("bulk.price","Price","Current listing price in CAD.","Set or override pricing in Bulk Editor, not Recognition Review.","Manual entry becomes authoritative; database suggestions never overwrite a deliberate operator value.",keywords=("price","manual")),
        HelpTopic("bulk.database_price","Database price","A prior strong SnapIMS product/edition match supplied the initial price.","Use as a speed-up for repeat inventory.","Prefills the price and visibly records DATABASE provenance; you may edit it.","Ambiguous same-title history is guidance only.",keywords=("database","pricing","history")),
        HelpTopic("bulk.ebay_sold","View eBay Sold","Open eBay Canada sold/completed results for the approved title plus VHS.","Use to manually verify market pricing, especially with two monitors.","Opens a new browser tab; no automated scraping is required.",keywords=("ebay","sold","comps")),
        HelpTopic("pricing.queue","eBay Pricing","Focused pricing queue/cache/collection workspace.","Use when you want dedicated market-evidence work beyond the Bulk Editor.","Preserves existing queue/cache behavior while keeping advanced collection controls secondary.",keywords=("ebay pricing","queue","cache")),
        HelpTopic("commit.commit_anyway","Commit Anyway","Finalize working records into authoritative SnapIMS inventory even when advisory warnings remain.","Use only after understanding the warning list.","Writes an auditable inventory commit boundary; warnings remain recorded.","Does not guarantee Shopify will accept an incomplete payload.",keywords=("commit","inventory","override")),
        HelpTopic("diagnostics.data_sources","Data Sources","Inspect the health and freshness of SnapIMS logical data sources without exposing secrets.","Use when you need to know whether inventory, metadata, pricing, Shopify, or eBay tooling is actually available.","Displays availability, record counts, freshness, and failure/degraded state.",keywords=("database","sources","diagnostics")),
        HelpTopic("settings.recognition","Recognition & AI settings","Configure recognition provider/model behavior.","Use when changing model/provider policy, not during normal review.","Affects future recognition requests; does not silently overwrite approved operator fields.",keywords=("settings","ai","model")),
        HelpTopic("settings.shopify","Publishing / Shopify settings","Configure Shopify store/auth/location/publication settings.","Use for integration setup or troubleshooting.","Controls Shopify API behavior; secrets remain protected.",keywords=("shopify","settings","publish")),
        HelpTopic("settings.general","General settings","Configure ordinary local SnapIMS defaults such as the incoming folder.","Use when changing a local application default.","Changes future workflow defaults without rewriting existing records.",keywords=("settings","general")),
        HelpTopic("settings.movie","Metadata / Catalog settings","Configure the local movie catalog and Wikipedia enrichment behavior.","Use when changing metadata provider, cache, retry, or provenance settings.","Affects nonblocking metadata enrichment; Recognition Review remains usable if metadata is unavailable.",keywords=("metadata","wikipedia","catalog")),
        HelpTopic("settings.infrastructure","Infrastructure settings","Inspect or configure installation infrastructure and remote-access endpoints.","Use for deployment/maintenance rather than normal tape processing.","Changes infrastructure behavior, not item metadata.",warnings="Do not expose secrets in screenshots or support bundles.",keywords=("infrastructure","remote")),
        HelpTopic("settings.security","Security settings","Configure authentication/session security.","Use only when administering SnapIMS access.","Changes operator authentication and session behavior.",warnings="Credential changes can revoke sessions; preserve recovery access.",keywords=("security","login","session")),
        HelpTopic("settings.backup","Backup & retention settings","Configure retention for backups, logs, and events.","Use when tuning storage/recovery policy.","Changes retention policy; it does not erase current working data immediately unless the existing maintenance workflow explicitly does so.",keywords=("backup","retention","recovery")),
    )
}

def get_topic(key: str) -> dict | None:
    topic = TOPICS.get(str(key or ""))
    return asdict(topic) if topic else None

def search_topics(query: str, *, limit: int = 20) -> list[dict]:
    needle = str(query or "").strip().casefold()
    if not needle:
        return [asdict(topic) for topic in list(TOPICS.values())[:limit]]
    matches=[]
    for topic in TOPICS.values():
        haystack=" ".join((topic.key,topic.title,topic.purpose,topic.when_to_use,*topic.keywords)).casefold()
        if needle in haystack:
            matches.append(asdict(topic))
        if len(matches)>=limit:
            break
    return matches

def assert_help_coverage(keys: Iterable[str]) -> None:
    missing=sorted({str(key) for key in keys if str(key) not in TOPICS})
    if missing:
        raise AssertionError("Missing contextual help registry entries: " + ", ".join(missing))


def generic_control_topic(*, label: str = "", kind: str = "control", name: str = "", form_action: str = "", href: str = "") -> dict:
    """Central fallback for ordinary controls without a hand-authored topic.

    This keeps F1/right-click coverage application-wide without declaring controls
    exempt. Hand-authored registry entries always take precedence.
    """
    clean_label = " ".join(str(label or name or kind or "Control").split())[:160]
    clean_kind = " ".join(str(kind or "control").split())[:80]
    action = str(form_action or "").strip()[:200]
    target = str(href or "").strip()[:200]
    purpose = f"Use {clean_label} in the current SnapIMS workflow."
    when = "Use this control when you intentionally want to change, navigate, filter, or run the action shown by its label."
    effect = "SnapIMS applies the control to the current page/workflow. Operator-entered values remain authoritative unless the feature explicitly documents otherwise."
    warnings = "This is semantic fallback help. Controls with special safety or workflow behavior have a dedicated help topic."
    if clean_kind in {"text", "search", "number", "password", "input", "textarea"}:
        purpose = f"Enter or edit {clean_label}."
        effect = "Changes the value submitted by the surrounding form or editor. Saving/submitting is still a separate operator action unless this field explicitly auto-applies."
    elif clean_kind in {"select", "dropdown"}:
        purpose = f"Choose the {clean_label} option."
        effect = "Changes the selected option for the current workflow or filter."
    elif clean_kind in {"button", "submit"}:
        purpose = f"Run {clean_label}."
        effect = f"Submits the surrounding SnapIMS action{(' (' + action + ')') if action else ''}."
    elif clean_kind in {"link", "a"}:
        purpose = f"Open {clean_label}."
        effect = f"Navigates to the related SnapIMS page or external destination{(' (' + target + ')') if target else ''}."
    return {
        "key": "auto", "title": clean_label or "SnapIMS control", "purpose": purpose,
        "when_to_use": when, "effect": effect, "warnings": warnings, "example": "",
        "related": [], "keywords": [clean_label.casefold(), clean_kind.casefold()],
    }
