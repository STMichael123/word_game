from storyweaver.engine import GameEngine


def test_export_contains_early_narrations_after_long_run() -> None:
    e = GameEngine()
    for i in range(25):
        e._record_story_memory(
            action=f'行动{i}',
            narration=f'这是第{i}段叙事原文',
            sim_result={'delta': {}, 'detail_lines': [f'细节{i}']},
            stage_notes=[],
        )
    out = e.export_story()
    assert '这是第0段叙事原文' in out
    assert '这是第24段叙事原文' in out
