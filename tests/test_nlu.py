from storyweaver.nlu import classify_intent_detailed, extract_target_detailed
from storyweaver.types import Intent


def test_intent_and_target_details() -> None:
    g1 = classify_intent_detailed('前往青石镇打听消息')
    assert g1.intent in {Intent.TRAVEL, Intent.QUERY}
    assert g1.confidence > 0.4

    t1 = extract_target_detailed('前往青石镇')
    assert t1.target == '青石镇'
    assert t1.confidence >= 0.8

    g2 = classify_intent_detailed('使用上品止血散')
    assert g2.intent == Intent.USE_ITEM
