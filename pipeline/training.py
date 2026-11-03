"""The Train half: which short module goes out with a reply, and the driver's own link to it. The training platform
(D Advaya FM naipuNya) holds one learner token per driver, minted when the driver is enrolled and kept in the private
registry; this module only chooses and builds the link. A page opened without a token is refused at the edge."""
BASE = "https://training.advayafm.com/lessons/"
LANG_INDEX = {"en": 0, "hi": 1, "te": 2}

# In the order they go out: one per accepted document. Titles in English, Hindi, Telugu.
MODULES = [
    ("tpt-vehicle", ("Vehicle care", "वाहन की देखभाल", "వాహన సంరక్షణ")),
    ("defensive-v2", ("Defensive driving", "सुरक्षित ड्राइविंग", "డిఫెన్సివ్ డ్రైవింగ్")),
    ("tpt-rules", ("Traffic rules", "ट्रैफ़िक नियम", "ట్రాఫిక్ నియమాలు")),
    ("roadsigns-v2", ("Road signs", "सड़क के संकेत", "రోడ్డు గుర్తులు")),
    ("tpt-risk", ("Safety and risk", "सुरक्षा और जोखिम", "భద్రత మరియు ప్రమాదం")),
    ("tpt-emergency", ("Emergencies on the road", "सड़क पर आपात स्थिति", "రోడ్డుపై అత్యవసర పరిస్థితులు")),
    ("firstaid-v4", ("First aid", "प्राथमिक उपचार", "ప్రథమ చికిత్స")),
    ("tpt-customer", ("Customer service", "ग्राहक सेवा", "కస్టమర్ సేవ")),
    ("tpt-basics", ("Basic driving skills", "बुनियादी ड्राइविंग", "ప్రాథమిక డ్రైవింగ్")),
    ("posh-drivers", ("POSH for drivers", "ड्राइवरों के लिए POSH", "డ్రైవర్ల కోసం POSH")),
]
TITLES = dict(MODULES)
ADVISORY_MODULE = "tpt-vehicle"          # a workshop advisory on the cab points at vehicle care first
ACCEPTED = {"accepted", "accepted_with_notes"}


def choose_module(opened_actions, already_sent) -> tuple | None:
    """(slug, reason) for the next module, or None once the driver has had them all."""
    if opened_actions and ADVISORY_MODULE not in already_sent:
        return ADVISORY_MODULE, "workshop advisory"
    for slug, _ in MODULES:
        if slug not in already_sent:
            return slug, "next in sequence"
    return None


def module_title(slug: str, lang: str = "en") -> str:
    return TITLES.get(slug, (slug, slug, slug))[LANG_INDEX.get(lang, 0)]


def module_link(slug: str, token: str) -> str:
    return "%s%s?k=%s" % (BASE, slug, token)
