"""Guards the HOAX_THRESHOLD margin. If you add hoaxes or tweak scoring, run this before the demo."""
import pytest

from app import config, hoax_matcher

HOAXES = [
    ("থানকুনি পাতা খান, করোনা হবে না", "thankuni-corona"),
    ("গরম পানি খেলে করোনা ভাইরাস মরে যায় সবাই জানুন", "hot-water-corona"),
    ("Salt will be 200 tk per kg soon, buy now", "salt-shortage"),
    ("লবণের দাম বাড়বে, এখনই কিনে রাখুন", "salt-shortage"),
    ("Scientists confirm the covid vaccine has a microchip inside", "vaccine-microchip"),
    ("আজ রাতে ঢাকায় বড় ভূমিকম্প হবে", "earthquake-tonight"),
    ("WhatsApp will charge money from next week, forward this", "whatsapp-charge"),
    ("Free laptop giveaway for students click here", "free-laptop"),
]

NEWS = [
    "Dhaka metro rail will run until midnight from next month",
    "প্রধানমন্ত্রী আজ নতুন সেতু উদ্বোধন করবেন",
    "Bangladesh Bank raised the policy interest rate today",
    "আজ ঢাকায় বৃষ্টি হতে পারে বলে জানিয়েছে আবহাওয়া অধিদপ্তর",
    "The government announced new vaccine campaign for children next week",
    "SSC exam results will be published tomorrow",
    "New Padma Bridge toll rates announced for trucks and buses",
    "করোনার টিকা নিতে নিবন্ধন করুন সুরক্ষা অ্যাপে",
    "Mobile operators to launch 5G service in Dhaka next year",
    "বাংলাদেশ ব্যাংক নতুন নোট ছাপানোর ঘোষণা দিয়েছে",
    "Dengue cases rise, doctors urge people to visit hospital early",
]


@pytest.mark.parametrize("text,hoax_id", HOAXES)
def test_hoax_paraphrases_match(text, hoax_id):
    m = hoax_matcher.best_match(text)
    assert m.entry["id"] == hoax_id and m.score >= config.HOAX_THRESHOLD, (m.entry["id"], m.score)


@pytest.mark.parametrize("text", NEWS)
def test_real_news_does_not_match(text):
    m = hoax_matcher.best_match(text)
    assert m.score < config.HOAX_THRESHOLD, (m.entry["id"], m.score)
