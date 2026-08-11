from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from snapims import db

@dataclass(frozen=True, slots=True)
class TagDefinition:
    label: str
    category: str

CATEGORIES: dict[str, tuple[str, ...]] = {
    "Core genres": ("action","adventure","animation","anime","biography","comedy","crime","documentary","drama","family","fantasy","film noir","history","horror","music","musical","mystery","romance","science fiction","sports","thriller","war","western"),
    "Action / Adventure": ("action comedy","action thriller","adventure comedy","adventure drama","disaster","espionage","heist","martial arts","military","samurai","superhero","survival","swashbuckler","vigilante"),
    "Comedy": ("black comedy","buddy comedy","comedy drama","family comedy","farce","mockumentary","parody","romantic comedy","satire","screwball comedy","sex comedy","slapstick","teen comedy"),
    "Horror": ("body horror","comedy horror","creature feature","folk horror","gothic horror","monster","occult","paranormal","psychological horror","slasher","splatter","supernatural horror","vampire","werewolf","zombie"),
    "Crime / Mystery / Thriller": ("crime drama","crime thriller","detective","gangster","legal drama","neo noir","police","political thriller","psychological thriller","serial killer","spy thriller","suspense","techno thriller"),
    "Science Fiction / Fantasy": ("apocalyptic","cyberpunk","dark fantasy","dystopian","epic fantasy","extraterrestrial","post apocalyptic","robot","space opera","steampunk","supernatural","time travel","virtual reality"),
    "Drama": ("coming of age","courtroom drama","family drama","historical drama","medical drama","melodrama","period drama","political drama","prison drama","religious drama","romantic drama","social drama","teen drama","tragedy"),
    "Family / Children": ("childrens","educational","fairy tale","kids animation","kids comedy","kids musical","preschool"),
    "Documentary / Nonfiction": ("concert","educational documentary","historical documentary","music documentary","nature documentary","sports documentary","travel","true crime"),
    "Sports": ("baseball","basketball","boxing","football","golf","hockey","motorsport","professional wrestling","soccer"),
    "Music": ("blues","classical music","country music","hip hop","jazz","pop music","rock music"),
    "Holiday": ("christmas","halloween","thanksgiving","valentines"),
    "Other": ("b movie","british","canadian","classic hollywood","cult","foreign film","hong kong cinema","independent","japanese cinema","made for television","miniseries","silent film"),
    "Franchise": ("alien franchise","american pie","austin powers","back to the future","barbie","batman","beavis and butt-head","beethoven","blade","care bears","childs play","children of the corn","die hard","dragon ball","ernest","evil dead","friday the 13th","ghostbusters","godzilla","goosebumps","halloween franchise","harry potter","hellraiser","herbie","highlander","home alone","indiana jones","james bond","jaws","jurassic park","land before time","looney tunes","lord of the rings","mad max","mighty morphin power rangers","muppets","nightmare on elm street","pokemon","rambo","rocky","rugrats","scooby-doo","scream","sesame street","south park","star trek","star wars","superman","teenage mutant ninja turtles","terminator","the flintstones","the mummy","the simpsons","thomas and friends","transformers","universal monsters","winnie the pooh","x-files","x-men"),
    "Animation / Brand": ("cartoon network","disney","dreamworks","hanna-barbera","jim henson","looney tunes","marvel","nickelodeon","pixar","sesame street","warner bros animation"),
    "Performer": ("al pacino","angelina jolie","arnold schwarzenegger","barbra streisand","betty white","brad pitt","bruce lee","bruce willis","carrie fisher","cher","chris farley","clint eastwood","dan aykroyd","demi moore","denzel washington","drew barrymore","eddie murphy","elizabeth taylor","gene hackman","gene wilder","george clooney","goldie hawn","harrison ford","jack nicholson","jackie chan","jamie lee curtis","jean-claude van damme","jim carrey","john candy","john travolta","jodie foster","julia roberts","julianne moore","keanu reeves","kevin costner","kurt russell","leonardo dicaprio","meg ryan","mel gibson","meryl streep","michael douglas","michelle pfeiffer","morgan freeman","nicole kidman","nicolas cage","patrick swayze","robert de niro","robin williams","sandra bullock","sean connery","sharon stone","sigourney weaver","steven seagal","susan sarandon","sylvester stallone","tom cruise","tom hanks","whoopi goldberg","will smith","winona ryder"),
}
DISALLOWED_AUTOMATIC = frozenset({"vhs","video","movie","film","classic","popular","blockbuster","award winning","retro","vintage","rare","collectible","must see","valuable"})

APPROVED_LABELS = tuple(dict.fromkeys(label for labels in CATEGORIES.values() for label in labels))
APPROVED_SET = frozenset(APPROVED_LABELS)
CATEGORY_BY_LABEL = {label: category for category, labels in CATEGORIES.items() for label in labels}

def tag_id(label: str) -> str:
    digest = hashlib.sha256(label.casefold().encode("utf-8")).hexdigest()[:16].upper()
    return f"TAG-{digest}"

TAG_BY_ID = {tag_id(label): label for label in APPROVED_LABELS}

def normalize_automatic_tags(values: Iterable[str], *, limit: int = 3) -> tuple[str, ...]:
    result: list[str] = []
    for raw in values:
        value = str(raw or "").strip().casefold()
        if not value or value in DISALLOWED_AUTOMATIC or value not in APPROVED_SET:
            continue
        if value not in result:
            result.append(value)
        if len(result) >= max(0, min(limit, 3)):
            break
    return tuple(result)

def normalize_automatic_tag_ids(values: Iterable[str], *, limit: int = 3) -> tuple[str, ...]:
    labels: list[str] = []
    for raw in values:
        text = str(raw or "").strip()
        label = TAG_BY_ID.get(text, text.casefold())
        if label in APPROVED_SET and label not in labels:
            labels.append(label)
        if len(labels) >= max(0, min(limit, 3)):
            break
    return tuple(tag_id(label) for label in labels)

def seed_approved_taxonomy(db_file: Path) -> int:
    """Upsert the closed AI taxonomy without deleting legacy/operator tags."""
    db.initialize(db_file)
    timestamp = db.now()
    changed = 0
    with db.transaction(db_file) as connection:
        for order, label in enumerate(APPROVED_LABELS, start=100):
            identifier = tag_id(label)
            category = CATEGORY_BY_LABEL[label]
            before = connection.execute(
                "SELECT tag_id,canonical_label,category,ai_eligible,active FROM tag_definitions WHERE canonical_label=? COLLATE NOCASE",
                (label,),
            ).fetchone()
            if before is None:
                connection.execute(
                    """INSERT INTO tag_definitions(
                        tag_id,canonical_label,category,active,ai_eligible,shopify_visible,
                        deterministic_only,sort_order,created_at,updated_at,evidence_json
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (identifier,label,category,1,1,1,0,order,timestamp,timestamp,
                     json.dumps({"source":"V016_OPERATOR_FIRST_APPROVED_TAXONOMY","closed_vocabulary":True},sort_keys=True)),
                )
                changed += 1
            else:
                connection.execute(
                    """UPDATE tag_definitions SET category=?,active=1,ai_eligible=1,shopify_visible=1,
                        deterministic_only=0,updated_at=?,evidence_json=? WHERE tag_id=?""",
                    (category,timestamp,json.dumps({"source":"V016_OPERATOR_FIRST_APPROVED_TAXONOMY","closed_vocabulary":True},sort_keys=True),str(before["tag_id"])),
                )
                if str(before["category"]) != category or not int(before["ai_eligible"]) or not int(before["active"]):
                    changed += 1
    return changed

def definitions() -> tuple[TagDefinition, ...]:
    return tuple(TagDefinition(label, CATEGORY_BY_LABEL[label]) for label in APPROVED_LABELS)
