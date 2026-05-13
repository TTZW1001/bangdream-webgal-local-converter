from __future__ import annotations

from pathlib import Path
import tempfile

from src.config_loader import load_config
from src.converter import convert_text
from src.figure_resource_index import scan_figure_directory
from src.models import FigureCharacterEntry, FigureModelEntry, FigureResourceIndex
from src.parser import parse_text
from src.speaker_resolver import SpeakerResolver


ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"


def test_config_loads_full_character_table() -> None:
    config = load_config(CONFIG_DIR)

    assert len(config.characters) >= 40
    assert config.aliases["灯"] == "tomori"
    assert config.characters["kasumi"].generic_character_id == "001"
    assert config.characters["taki"].generic_character_id == "040"


def test_figure_index_scans_legacy_directory_and_maps_character() -> None:
    config = load_config(CONFIG_DIR)
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        legacy_dir = root / "户山 香澄" / "casual"
        legacy_dir.mkdir(parents=True, exist_ok=True)
        (legacy_dir / "idle01_default.png").write_bytes(b"png")
        (legacy_dir / "idle01_smile.png").write_bytes(b"png")

        index = scan_figure_directory(root, config)

        assert "户山 香澄" in index.characters
        character = index.characters["户山 香澄"]
        assert character.mapped_character_id == "kasumi"
        assert "casual" in character.models
        assert character.models["casual"].resource_type == "legacy"
        assert character.models["casual"].motions == ["idle01"]
        assert character.models["casual"].expressions == ["default", "smile"]


def test_figure_index_scans_live2d_directory_and_extracts_model_json_data() -> None:
    config = load_config(CONFIG_DIR)
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        model_dir = root / "anon" / "school_winter-2023"
        model_dir.mkdir(parents=True, exist_ok=True)
        (model_dir / "texture_00.png").write_bytes(b"png")
        (model_dir / "model.json").write_text(
            """
            {
              "motions": {
                "idle": { "File": "anon/idle01.motion3.json" },
                "wave": { "File": "anon/wave01.motion3.json" }
              },
              "expressions": [
                { "File": "anon/default.exp3.json" },
                { "File": "anon/smile.exp3.json" }
              ]
            }
            """.strip(),
            encoding="utf-8",
        )

        index = scan_figure_directory(root, config)

        assert "anon" in index.characters
        character = index.characters["anon"]
        assert character.mapped_character_id == "anon"
        assert "school_winter-2023" in character.models
        model = character.models["school_winter-2023"]
        assert model.resource_type == "live2d_json"
        assert model.model_path == "anon/school_winter-2023/model.json"
        assert model.motions == ["idle01", "wave01"]
        assert model.expressions == ["default", "smile"]


def test_figure_index_manual_mapping_overrides_auto_resolution() -> None:
    config = load_config(CONFIG_DIR)
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        legacy_dir = root / "小香香" / "default"
        legacy_dir.mkdir(parents=True, exist_ok=True)
        (legacy_dir / "idle01_default.png").write_bytes(b"png")

        index = scan_figure_directory(root, config, manual_mappings={"小香香": "kasumi"})

        character = index.characters["小香香"]
        assert character.mapped_character_id == "kasumi"
        assert character.mapping_source == "manual"


def test_figure_index_ignores_live2d_texture_pngs_inside_model_tree() -> None:
    config = load_config(CONFIG_DIR)
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        model_dir = root / "misaki" / "live2d" / "chara" / "015_4th_general_election_r_rip"
        model_dir.mkdir(parents=True, exist_ok=True)
        (model_dir / "model.json").write_text(
            """
            {
              "motions": {
                "idle": { "File": "misaki/idle01.motion3.json" }
              },
              "expressions": [
                { "File": "misaki/default.exp3.json" }
              ]
            }
            """.strip(),
            encoding="utf-8",
        )
        (model_dir / "texture_01.png").write_bytes(b"png")
        (model_dir / "texture_02.png").write_bytes(b"png")

        index = scan_figure_directory(root, config)

        assert "misaki" in index.characters
        character = index.characters["misaki"]
        assert len(character.models) == 1
        model = character.models["015_4th_general_election_r_rip"]
        assert model.resource_type == "live2d_json"
        assert model.model_path == "misaki/live2d/chara/015_4th_general_election_r_rip/model.json"


def test_figure_index_scans_legacy_model_json_files() -> None:
    config = load_config(CONFIG_DIR)
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        character_dir = root / "hagumi"
        character_dir.mkdir(parents=True, exist_ok=True)
        (character_dir / "013_casual-2023model.json").write_text(
            """
            {
              "motions": {
                "idle": [{ "file": "live2d/chara/013_general_rip/idle01.mtn" }]
              },
              "expressions": [
                { "name": "default", "file": "live2d/chara/013_general_rip/default.exp.json" },
                { "name": "smile01", "file": "live2d/chara/013_general_rip/smile01.exp.json" }
              ]
            }
            """.strip(),
            encoding="utf-8",
        )

        index = scan_figure_directory(root, config)

        character = index.characters["hagumi"]
        model = character.models["casual-2023"]
        assert model.resource_type == "legacy_json"
        assert model.model_path == "hagumi/013_casual-2023model.json"
        assert model.motions == ["idle01"]
        assert model.expressions == ["default", "smile01"]


def test_scene_config_loads_structured_rules_with_legacy_fallback() -> None:
    config = load_config(CONFIG_DIR)

    assert config.scene_config.rules["学生会室"] == "student_council_room"
    assert config.scene_config.aliases["弦卷家会议室"] == "kokoro_meeting_room"
    assert config.scene_config.scenes["campus"]["variants"]["花咲川"]["times"]["黄昏"] == "学校、工作/花咲川/花咲川校园（黄昏）.png"
    assert config.scene_config.scenes["park"]["times"]["夜晚"] == "公园/公园1（晚上）.png"
    assert config.scene_config.scenes["circle_front"]["times"]["黄昏"] == "演出、排练/CiRCLE/CiRCLE前台（黄昏）.png"
    assert config.scene_keywords["公园"] == "公园/公园1（白天）.png"


def test_parser_detects_dialogue_forms() -> None:
    segments = parse_text("灯：你好\n\n爱音说：“还没回去吗？”\n\n“……嗯。”")

    assert [segment.speaker_hint for segment in segments] == ["灯", "爱音", None]
    assert [segment.text for segment in segments] == ["你好", "还没回去吗？", "……嗯。"]


def test_parser_tolerates_unclosed_quote_line() -> None:
    segments = parse_text("“市谷同学别说笑啦—……")

    assert len(segments) == 1
    assert segments[0].kind.value == "dialogue"
    assert segments[0].text == "市谷同学别说笑啦—……"


def test_parser_splits_quote_action_quote_into_three_parts() -> None:
    segments = parse_text("“只是有点低烧啦。”美咲摆摆手，“不影响工作的。”")

    assert [segment.kind.value for segment in segments] == ["dialogue", "narration", "dialogue"]
    assert segments[0].text == "只是有点低烧啦。"
    assert segments[1].text == "美咲摆摆手"
    assert segments[2].text == "不影响工作的。"
    assert segments[0].speaker_hint == "美咲摆摆手"
    assert segments[2].speaker_hint == "美咲摆摆手"


def test_parser_splits_quote_action_quote_with_new_action_marker() -> None:
    segments = parse_text("“那个……”美咲清了清嗓子，“这段时间谢谢大家的关心，我已经没事了。”")

    assert [segment.kind.value for segment in segments] == ["dialogue", "narration", "dialogue"]
    assert segments[0].text == "那个……"
    assert segments[1].text == "美咲清了清嗓子"
    assert segments[2].text == "这段时间谢谢大家的关心，我已经没事了。"


def test_parser_keeps_two_embedded_quoted_terms_inside_narration() -> None:
    text = "美咲把手机扣在床上，还要陪着心到处实现什么“让世界充满笑容”的童话计划……但那只是自己责任感作祟吧！跟心只是普通的朋友关系，怎么可能到“单恋”这种程度！"
    segments = parse_text(text)

    assert len(segments) == 1
    assert segments[0].kind.value == "narration"
    assert "让世界充满笑容" in segments[0].text
    assert "单恋" in segments[0].text


def test_parser_keeps_quote_example_lines_as_narration() -> None:
    segments = parse_text("……总不能当着育美的面问：“心~你知道什么是喜欢吗？”。")

    assert len(segments) == 1
    assert segments[0].kind.value == "narration"


def test_parser_keeps_quote_term_with_predicate_as_narration() -> None:
    segments = parse_text("“Hello Happy观察美咲计划”还在热火朝天地进行着。")

    assert len(segments) == 1
    assert segments[0].kind.value == "narration"


def test_parser_treats_quote_only_after_narration_colon_as_narration() -> None:
    segments = parse_text("心肯定只会说：\n“当然啊！我喜欢大家的笑容！我最喜欢大家了！”")

    assert [segment.kind.value for segment in segments] == ["narration", "narration"]


def test_parser_preserves_action_quote_action_quote_dialogue() -> None:
    segments = parse_text("“学生会可以晚一点再去啦！”心回头笑，“现在有更重要的事情！”")

    assert [segment.kind.value for segment in segments] == ["dialogue", "narration", "dialogue"]
    assert segments[0].speaker_hint == "心回头笑"
    assert segments[2].speaker_hint == "心回头笑"


def test_parser_splits_single_quote_with_trailing_action() -> None:
    segments = parse_text("“还有！”育美眼睛一亮")

    assert [segment.kind.value for segment in segments] == ["dialogue", "narration"]
    assert segments[0].text == "还有！"
    assert segments[0].speaker_hint == "育美眼睛一亮"
    assert segments[1].text == "育美眼睛一亮"


def test_speaker_resolver_uses_recent_single_mention() -> None:
    config = load_config(CONFIG_DIR)
    segments = parse_text("灯低头看着歌词本。\n\n“……还是写不好。”")
    resolved, pending = SpeakerResolver(config).resolve(segments)

    assert not pending
    assert resolved[1].speaker_id == "tomori"


def test_speaker_hint_with_single_char_alias_and_action_resolves_speaker() -> None:
    config = load_config(CONFIG_DIR)
    speaker_id = SpeakerResolver(config).resolve_speaker_hint("心兴致勃勃看着美咲")

    assert speaker_id == "kokoro"


def test_quote_action_quote_resolves_same_speaker() -> None:
    result = convert_text("“只是有点低烧啦。”美咲摆摆手，“不影响工作的。”", CONFIG_DIR)

    assert "奥泽美咲:只是有点低烧啦。 -id -figureId=misaki;" in result.script
    assert ":美咲摆摆手;" in result.script
    assert "奥泽美咲:不影响工作的。 -id -figureId=misaki;" in result.script


def test_speaker_override_can_force_dialogue_to_narration() -> None:
    result = convert_text("“只是举例，不是对白。”", CONFIG_DIR, speaker_overrides={0: "kind:narration"})

    assert result.script.endswith(":只是举例，不是对白。;\n")
    assert "未知:" not in result.script


def test_speaker_override_can_force_narration_to_dialogue() -> None:
    result = convert_text("只是刚好被错分成旁白。", CONFIG_DIR, speaker_overrides={0: "char:misaki"})

    assert "奥泽美咲:只是刚好被错分成旁白。 -id -figureId=misaki;" in result.script
    assert ":只是刚好被错分成旁白。;" not in result.script


def test_custom_name_override_can_force_narration_to_dialogue() -> None:
    result = convert_text("老师敲了敲门。", CONFIG_DIR, speaker_overrides={0: "name:老师"})

    assert "老师:老师敲了敲门。;" in result.script


def test_addressing_other_character_prefers_the_other_speaker_in_two_person_scene() -> None:
    text = "\n".join(
        [
            "美咲推开学生会室的门。",
            "有咲抱着文件走进来。",
            "“咳、咳——”",
            "“喂喂，奥泽同学你没事吧？”",
        ]
    )

    result = convert_text(text, CONFIG_DIR)

    assert "奥泽美咲:咳、咳—— -id -figureId=misaki;" in result.script
    assert "有咲:喂喂，奥泽同学你没事吧？ -id -figureId=arisa;" in result.script


def test_next_narration_actor_can_claim_short_reaction_dialogue() -> None:
    text = "\n".join(
        [
            "美咲推开学生会室的门。",
            "有咲抱着文件走进来。",
            "“下午好啊，奥泽会长。”",
            "“恕我直言……你脸色怎么这么差？”",
        ]
    )

    result = convert_text(text, CONFIG_DIR)

    assert "有咲:下午好啊，奥泽会长。 -id -figureId=arisa;" in result.script
    assert "有咲:恕我直言……你脸色怎么这么差？ -id -figureId=arisa;" in result.script


def test_address_suffix_can_keep_followup_dialogue_on_same_other_speaker() -> None:
    text = "\n".join(
        [
            "美咲推开学生会室的门。",
            "有咲抱着文件走进来。",
            "“怎么说这种设定都不会在现实中发生吧……”",
            "有咲耸了耸肩。",
            "“谁知道呢……这世界不合理的事情太多了。”",
            "“当然，刚刚也只是我的猜测，毕竟奥泽同学你的症状和这个设定太像了……”",
        ]
    )

    result = convert_text(text, CONFIG_DIR)

    assert "奥泽美咲:怎么说这种设定都不会在现实中发生吧…… -id -figureId=misaki;" in result.script
    assert "有咲:谁知道呢……这世界不合理的事情太多了。 -id -figureId=arisa;" in result.script
    assert "有咲:当然，刚刚也只是我的猜测，毕竟奥泽同学你的症状和这个设定太像了…… -id -figureId=arisa;" in result.script


def test_addressed_character_can_claim_immediate_response_dialogue() -> None:
    text = "\n".join(
        [
            "美咲推开学生会室的门。",
            "有咲抱着文件走进来。",
            "“咳、咳——”",
            "“喂喂，奥泽同学你没事吧？”",
            "“没……没事，就是嗓子有点——咳！”",
        ]
    )

    result = convert_text(text, CONFIG_DIR)

    assert "奥泽美咲:咳、咳—— -id -figureId=misaki;" in result.script
    assert "有咲:喂喂，奥泽同学你没事吧？ -id -figureId=arisa;" in result.script
    assert "奥泽美咲:没……没事，就是嗓子有点——咳！ -id -figureId=misaki;" in result.script


def test_addressed_character_can_claim_short_followup_reply() -> None:
    text = "\n".join(
        [
            "美咲看向心。",
            "“心有喜欢的人吗？”",
            "“有的哦！”",
        ]
    )

    result = convert_text(text, CONFIG_DIR)

    assert "弦卷心:有的哦！ -id -figureId=kokoro;" in result.script


def test_first_person_confession_line_can_stay_with_current_speaker() -> None:
    text = "\n".join(
        [
            "美咲和心站在天台。",
            "“但是我不一样。我喜欢她，不是朋友那种。”",
            "“我喜欢的人是你，心。”",
        ]
    )

    result = convert_text(text, CONFIG_DIR)

    assert "奥泽美咲:我喜欢的人是你，心。 -id -figureId=misaki;" in result.script


def test_followup_entry_question_stays_with_entering_speaker() -> None:
    text = "\n".join(
        [
            "门在这时被推开。",
            "“下午好啊，奥泽会长。”",
            "副会长有咲抱着一叠文件走进来，刚把东西放到桌上，就皱了皱眉。",
            "“恕我直言……你脸色怎么这么差？”",
            "美咲抬头笑了一下：“有吗？可能是昨天演出有点累吧。”",
        ]
    )

    result = convert_text(text, CONFIG_DIR)

    assert "有咲:下午好啊，奥泽会长。 -id -figureId=arisa;" in result.script
    assert "有咲:恕我直言……你脸色怎么这么差？ -id -figureId=arisa;" in result.script
    assert "奥泽美咲:有吗？可能是昨天演出有点累吧。 -id -figureId=misaki;" in result.script


def test_address_memory_clears_before_internal_monologue() -> None:
    text = "\n".join(
        [
            "“下午好啊，奥泽会长。”",
            "副会长有咲抱着一叠文件走进来。",
            "“恕我直言……你脸色怎么这么差？”",
            "“有吗？可能是昨天演出有点累吧。”",
            "比如说……市谷有咲同学？",
            "美咲刚想到这个名字，又很快否定了。",
            "“不对吧，我跟她也没那么熟……”",
        ]
    )

    result = convert_text(text, CONFIG_DIR)

    assert "奥泽美咲:不对吧，我跟她也没那么熟…… -id -figureId=misaki;" in result.script


def test_quote_only_dialogue_with_setting_word_stays_dialogue() -> None:
    segments = parse_text("“反正这种设定本来就很离谱……先睡一觉吧，万一一早起来就好了呢。”")

    assert len(segments) == 1
    assert segments[0].kind.value == "dialogue"
    assert segments[0].text == "反正这种设定本来就很离谱……先睡一觉吧，万一一早起来就好了呢。"


def test_end_to_end_generates_webgal_script() -> None:
    text = (ROOT / "samples" / "input_01.txt").read_text(encoding="utf-8")
    result = convert_text(text, CONFIG_DIR)

    assert "changeBg:" in result.script
    assert "灯:……还是写不好。 -id -figureId=tomori;" in result.script
    assert "爱音:灯，还没回去吗？ -id -figureId=anon;" in result.script


def test_line_based_fanfic_with_inline_quote() -> None:
    text = "\n".join(
        [
            "清晨，立希走进教室，一到座位上就趴了下来。",
            "海铃走到旁边：“立希同学，昨天不会又熬夜写曲子了吧……身体还要不要了？”",
            "说着，海铃把立希最喜欢的熊猫奶冻放在了立希头上。",
        ]
    )

    result = convert_text(text, CONFIG_DIR)

    assert ":海铃走到旁边;" in result.script
    assert "海铃:立希同学，昨天不会又熬夜写曲子了吧……身体还要不要了？ -id -figureId=umiri;" in result.script
    assert ":说着，海铃把立希最喜欢的熊猫奶冻放在了立希头上。;" in result.script


def test_first_two_figures_use_left_and_right() -> None:
    result = convert_text("灯：你好\n爱音：你好呀", CONFIG_DIR)

    assert "changeFigure:tomori/036_school_winter-2023model.json -id=tomori -motion=idle01 -expression=default -left -next;" in result.script
    assert "changeFigure:anon/037_school_winter-2023model.json -id=anon -motion=idle01 -expression=default -right -next;" in result.script


def test_narration_mentions_enter_stage_and_dialogue_alternates() -> None:
    text = "\n".join(
        [
            "清晨，立希走进教室，一到座位上就趴了下来。",
            "海铃走到旁边：“立希同学，昨天不会又熬夜写曲子了吧……身体还要不要了？”",
            "说着，海铃把立希最喜欢的熊猫奶冻放在了立希头上。",
            "“……”",
            "“我说海铃……你今天怎么来那么早？”",
        ]
    )

    result = convert_text(text, CONFIG_DIR)

    assert "changeFigure:taki/school_winter-2023/model.json" in result.script
    assert "立希:…… -id -figureId=taki;" in result.script
    assert "立希:我说海铃……你今天怎么来那么早？ -id -figureId=taki;" in result.script


def test_unknown_speaker_keeps_name_and_scene_change_closes_figures() -> None:
    text = "\n".join(
        [
            "早上，心走进教室。",
            "老师从门口走进来：“限时10分钟啊，准时收卷。”",
            "中午，心来到中庭。",
            "心：吃午饭啦！",
        ]
    )

    result = convert_text(text, CONFIG_DIR)

    assert "老师:限时10分钟啊，准时收卷。;" in result.script
    assert "changeFigure: -id=kokoro -next;" in result.script
    assert "changeBg:学校、工作/花咲川/花咲川校园（白天）.png -next;" in result.script


def test_generic_school_scene_uses_character_school_context() -> None:
    text = "\n".join(
        [
            "清晨，立希走进教室，一到座位上就趴了下来。",
            "海铃走到旁边：“立希同学，今天来得真早。”",
            "中午，立希和海铃一如既往来到了中庭进食午餐。",
        ]
    )

    result = convert_text(text, CONFIG_DIR)

    assert "changeBg:学校、工作/花咲川/花咲川教室（白天）.png -next;" in result.script
    assert "changeBg:学校、工作/花咲川/花咲川校园（白天）.png -next;" in result.script


def test_manual_school_context_overrides_generic_school_scene() -> None:
    result = convert_text("清晨，学生走进教室。", CONFIG_DIR, scene_school="月之森")

    assert "changeBg:学校、工作/月之森/月之森教室（白天）.png -next;" in result.script


def test_school_time_context_uses_selected_school_for_after_school_scene() -> None:
    result = convert_text("隔天放学后。", CONFIG_DIR, scene_school="花咲川")

    assert result.script.startswith("changeBg:学校、工作/花咲川/花咲川校园（黄昏）.png -next;")


def test_school_context_prefers_selected_student_council_room() -> None:
    result = convert_text("隔天放学后，美咲站在学生会室门口。", CONFIG_DIR, scene_school="花咲川")

    assert "changeBg:学校、工作/花咲川/花咲川学生会活动室（黄昏）.png -next;" in result.script


def test_scene_alias_detects_tsurumaki_meeting_room() -> None:
    result = convert_text("弦卷家会议室。", CONFIG_DIR)

    assert "changeBg:角色生活地点/hello happy world/弦卷心家会议室.png -next;" in result.script


def test_structured_scene_uses_time_variant_for_park() -> None:
    result = convert_text("傍晚，大家走到公园里散步。", CONFIG_DIR)

    assert "changeBg:公园/公园1（黄昏）.png -next;" in result.script


def test_structured_scene_uses_time_variant_for_circle_front() -> None:
    result = convert_text("黄昏时分，大家在CiRCLE碰面。", CONFIG_DIR)

    assert "changeBg:演出、排练/CiRCLE/CiRCLE前台（黄昏）.png -next;" in result.script


def test_structured_scene_detects_character_room() -> None:
    result = convert_text("夜里，爱音回到自己的房间。爱音的房间里安静得只剩空调声。", CONFIG_DIR)

    assert "changeBg:角色生活地点/mygo/爱音的房间（晚上）.png -next;" in result.script


def test_structured_scene_detects_house_entrance_time_variant() -> None:
    result = convert_text("傍晚时，爱音家门口停着一辆熟悉的车。", CONFIG_DIR)

    assert "changeBg:角色生活地点/mygo/爱音家门口（黄昏无车）.png -next;" in result.script


def test_structured_scene_detects_mujica_related_space() -> None:
    result = convert_text("演出结束后，大家回到休息室整理东西。", CONFIG_DIR)

    assert "changeBg:演出、排练/Mujica相关/休息室.jpg -next;" in result.script


def test_structured_scene_detects_park_stage_time_variant() -> None:
    result = convert_text("夜晚的公园舞台灯光渐渐亮起。", CONFIG_DIR)

    assert "changeBg:演出、排练/其他演出场地/公园舞台-大（晚上）.png -next;" in result.script


def test_structured_scene_detects_mygo_family_living_room() -> None:
    result = convert_text("晚饭后，立希家客厅里只剩下电视的声音。", CONFIG_DIR)

    assert "changeBg:角色生活地点/mygo/立希家客厅.jpg -next;" in result.script


def test_structured_scene_detects_hhw_castle_square() -> None:
    result = convert_text("夜晚的快乐国广场依旧热闹。", CONFIG_DIR)

    assert "changeBg:角色生活地点/hello happy world/快乐国广场（庆典夜晚）.png -next;" in result.script


def test_structured_scene_detects_popipa_store() -> None:
    result = convert_text("大家约在流星堂门口集合。", CONFIG_DIR)

    assert "changeBg:角色生活地点/popipa/有咲家的流星堂.png -next;" in result.script


def test_structured_scene_detects_auditorium_entrance_time_variant() -> None:
    result = convert_text("晚上，众人来到演出厅门口等待入场。", CONFIG_DIR)

    assert "changeBg:演出、排练/其他演出场地/演出厅门口（晚上）.png -next;" in result.script


def test_structured_scene_detects_agency_exterior_time_variant() -> None:
    result = convert_text("深夜的经纪公司外冷冷清清。", CONFIG_DIR)

    assert "changeBg:演出、排练/Mujica相关/经纪公司外夜.jpg -next;" in result.script


def test_generic_alias_expansion_resolves_room_without_de() -> None:
    result = convert_text("夜里，美咲房间里还亮着灯。", CONFIG_DIR)

    assert "changeBg:角色生活地点/hello happy world/美咲的房间.png -next;" in result.script


def test_generic_alias_expansion_resolves_home_living_room_phrase() -> None:
    result = convert_text("晚饭后，立希家里安静得只剩钟表声。", CONFIG_DIR)

    assert "changeBg:角色生活地点/mygo/立希家客厅.jpg -next;" in result.script


def test_generic_alias_expansion_resolves_home_entrance_without_family_marker() -> None:
    result = convert_text("黄昏时，爱音门口停着一辆熟悉的车。", CONFIG_DIR)

    assert "changeBg:角色生活地点/mygo/爱音家门口（黄昏无车）.png -next;" in result.script


def test_generic_alias_expansion_resolves_home_exterior_variant() -> None:
    result = convert_text("白天，立希家外安静得只有风声。", CONFIG_DIR)

    assert "changeBg:角色生活地点/mygo/立希家外部（白天）.jpg -next;" in result.script


def test_generic_alias_expansion_resolves_circle_lobby_phrase() -> None:
    result = convert_text("黄昏时，大家在CiRCLE大厅集合。", CONFIG_DIR)

    assert "changeBg:演出、排练/CiRCLE/CiRCLE前台（黄昏）.png -next;" in result.script


def test_generic_alias_expansion_resolves_ring_lobby_phrase() -> None:
    result = convert_text("大家在RiNG大厅等着开门。", CONFIG_DIR)

    assert "changeBg:演出、排练/RiNG/RiNG前台.png -next;" in result.script


def test_initial_scene_prefers_explicit_location_over_after_school_ambience() -> None:
    text = "\n".join(
        [
            "隔天放学后。",
            "“那个……市谷同学。”",
            "美咲站在学生会室门口，轻轻敲了敲门。",
        ]
    )

    result = convert_text(text, CONFIG_DIR)

    assert result.script.startswith("changeBg:学校、工作/花咲川/花咲川学生会活动室（黄昏）.png -next;")
    assert "羽丘校园（黄昏）" not in result.script


def test_scene_discussion_does_not_switch_to_literal_stage() -> None:
    result = convert_text(
        "\n".join(
            [
                "弦卷家会议室。",
                "Hello Happy五人到齐。",
                "不过还是得先阻止”舞台上飘洒大量花瓣雨“这种离谱的设定才行。",
            ]
        ),
        CONFIG_DIR,
    )

    assert "changeBg:角色生活地点/hello happy world/弦卷心家会议室.png -next;" in result.script
    assert "临时舞台（白天）" not in result.script


def test_student_council_dialogue_alternation_stays_on_misaki_and_arisa() -> None:
    text = "\n".join(
        [
            "隔天放学后。",
            "“那个……市谷同学。”",
            "美咲站在学生会室门口，轻轻敲了敲门。",
            "有咲正埋头整理文件，听见声音抬起头。",
            "“嗯？”",
            "“前几天你好像找我有事……那时候我正好有事没能过去，抱歉。”",
            "“哦那个啊，没事。”有咲摆了摆手，。",
            "“其实也不是什么重要的事，本来就是想问你最近怎么样。”",
            "“结果北泽同学听一半就跑去找你了，我也没说清楚。”",
            "“我这边也有问题，不用在意。”",
            "“哦？”",
        ]
    )

    result = convert_text(text, CONFIG_DIR)

    assert "奥泽美咲:前几天你好像找我有事……那时候我正好有事没能过去，抱歉。 -id -figureId=misaki;" in result.script
    assert "有咲:其实也不是什么重要的事，本来就是想问你最近怎么样。 -id -figureId=arisa;" in result.script
    assert "奥泽美咲:我这边也有问题，不用在意。 -id -figureId=misaki;" in result.script
    assert "有咲:哦？ -id -figureId=arisa;" in result.script
    assert "北泽育美:" not in result.script


def test_hhw_meeting_dialogue_keeps_speakers_on_reply_chain() -> None:
    text = "\n".join(
        [
            "弦卷家会议室。",
            "Hello Happy五人到齐。",
            "“那个……”美咲清了清嗓子，“这段时间谢谢大家的关心，我已经没事了。”",
            "“接下来我们来讨论一下下次的Live吧……”",
            "“太好了小美！”育美“啪”地一声把一大盘东西放到桌上，“我带了新出炉的可乐饼！”",
            "“来庆祝小美恢复健康！”",
            "“呼诶诶……”花音被吓了一跳，“这么多会不会吃不完啊……”",
            "“恭喜你恢复健康哦，小美咲。”",
            "“谢、谢谢……那下次的Live……”",
            "“美咲和我在一起了哦！”",
            "“心！！这种事情不要在会议上直接说啊！！”",
            "“欸——？！”育美眼睛瞬间亮了，",
            "“原来小美喜欢的是小心心！”",
            "“而且小心心也喜欢小美！太好了！！”",
            "“快吃！庆祝一下！”",
            "“等等这逻辑是怎么跳过去的——”",
            "“恭喜你，小美咲。”连花音也笑着祝福。",
            "“祝你和心心幸福……”",
            "“花音学姐你怎么也……”",
            "薰显然还不打算收手，继续火上浇油。",
            "“既然如此，下次的Live——不如让舞台开满象征爱情的花如何？”",
            "“因为Hello Happy要把快乐带给全世界嘛！”心兴致勃勃看着美咲。",
            "“我病才刚好……你们就要搞这种大工程吗……”",
            "心从正面抱住了她，像太阳一样的笑容挂在脸上。",
            "“因为美咲已经回来了呀！”",
        ]
    )

    result = convert_text(text, CONFIG_DIR)

    assert "奥泽美咲:等等这逻辑是怎么跳过去的—— -id -figureId=misaki;" in result.script
    assert "奥泽美咲:花音学姐你怎么也…… -id -figureId=misaki;" in result.script
    assert "弦卷心:因为美咲已经回来了呀！ -id -figureId=kokoro;" in result.script


def test_generic_alias_expansion_resolves_kokoro_side_gate_phrase() -> None:
    result = convert_text("晚上，心侧门那边忽然传来脚步声。", CONFIG_DIR)

    assert "changeBg:角色生活地点/hello happy world/弦卷心家侧门（晚上）.png -next;" in result.script


def test_generic_alias_expansion_resolves_home_genkan_phrase() -> None:
    result = convert_text("诗船门厅里传来轻轻的脚步声。", CONFIG_DIR)

    assert "changeBg:角色生活地点/mygo/诗船家玄关.png -next;" in result.script


def test_generic_alias_expansion_resolves_home_courtyard_phrase() -> None:
    result = convert_text("黄昏时，诗船院子里吹来一阵风。", CONFIG_DIR)

    assert "changeBg:角色生活地点/mygo/诗船家中庭.png -next;" in result.script


def test_generic_alias_expansion_resolves_backstage_synonym() -> None:
    result = convert_text("演出结束后，大家都回到了CiRCLE后场。", CONFIG_DIR)

    assert "changeBg:演出、排练/CiRCLE/CiRCLE后台.png -next;" in result.script


def test_generic_alias_expansion_resolves_rest_area_synonym() -> None:
    result = convert_text("Mujica休息区里还残留着刚才演出的热气。", CONFIG_DIR)

    assert "changeBg:演出、排练/Mujica相关/休息室.jpg -next;" in result.script


def test_inline_and_quote_followup_dialogue_resolves_mygo_speakers() -> None:
    text = "\n".join(
        [
            "爱音挠挠头：“不好意思啦Rikki~曲子昨天才拿到手还没时间练习，下次一定能完整流利弹下来的！”灯看着斗志昂扬的爱音，也对立希说：“……小立希要相信小爱音哦。”灯都这么说了……那先放那家伙一马吧。立希想着，叹了口气。",
            "“Rikki，抹茶芭菲。”乐奈又凑了上来，拉了拉立希的袖子。",
            "“野猫。练习还没结束，等一下吃。”",
            "“不要，现在就要吃。”",
            "立希有点头疼，乐奈还是老样子不听人说话啊，素世赶忙救场。",
            "“小乐奈，先吃块金平糖吧~听小立希的话哦！”",
        ]
    )

    result = convert_text(text, CONFIG_DIR)

    assert not result.pending_items
    assert "爱音:不好意思啦Rikki~曲子昨天才拿到手还没时间练习，下次一定能完整流利弹下来的！ -id -figureId=anon;" in result.script
    assert "灯:……小立希要相信小爱音哦。 -id -figureId=tomori;" in result.script
    assert "乐奈:Rikki，抹茶芭菲。 -id -figureId=rana;" in result.script
    assert "立希:野猫。练习还没结束，等一下吃。 -id -figureId=taki;" in result.script
    assert "乐奈:不要，现在就要吃。 -id -figureId=rana;" in result.script
    assert "素世:小乐奈，先吃块金平糖吧~听小立希的话哦！ -id -figureId=soyo;" in result.script
    assert "changeFigure: -id=" in result.script


def test_multi_party_reverse_address_can_infer_called_speaker() -> None:
    text = "\n".join(
        [
            "美咲还想继续说些什么，却被打断。",
            "“美咲~~~~！”",
            "“喂！心——！”",
        ]
    )

    result = convert_text(text, CONFIG_DIR)

    assert "弦卷心:美咲~~~~！ -id -figureId=kokoro;" in result.script
    assert "奥泽美咲:喂！心——！ -id -figureId=misaki;" in result.script


def test_explicit_speaker_clue_can_continue_same_speaker_in_multi_party_scene() -> None:
    text = "\n".join(
        [
            "弦卷家会议室。",
            "Hello Happy五人到齐。",
            "“太好了小美！”育美“啪”地一声把一大盘东西放到桌上，“我带了新出炉的可乐饼！”",
            "“来庆祝小美恢复健康！”",
        ]
    )

    result = convert_text(text, CONFIG_DIR)

    assert "北泽育美:我带了新出炉的可乐饼！ -id -figureId=hagumi;" in result.script
    assert "北泽育美:来庆祝小美恢复健康！ -id -figureId=hagumi;" in result.script


def test_speaker_override_can_fix_dialogue_segment() -> None:
    result = convert_text("“还没回去吗？”", CONFIG_DIR, speaker_overrides={0: "anon"})

    assert not result.pending_items
    assert "爱音:还没回去吗？ -id -figureId=anon;" in result.script


def test_custom_speaker_override_outputs_name_without_figure() -> None:
    result = convert_text("“欢迎光临。”", CONFIG_DIR, speaker_overrides={0: "name:店员"})

    assert not result.pending_items
    assert "店员:欢迎光临。;" in result.script
    assert "figureId" not in result.script


def test_hhw_stage_dialogue_and_scene_context_stay_stable() -> None:
    text = "\n".join(
        [
            "十月的秋风早已带上些许凉意。",
            "奥泽美咲站在公园里搭建的临时舞台后方，一如既往穿着米歇尔厚重的玩偶服，操作着DJ混音台，引导观众的气氛。",
            "“大家——！今天也要尽情欢笑哦——！”",
            "演出即将结束，心照例扑向米歇尔，以热烈快乐的拥抱结束这首曲目。美咲早已调整好重心站稳脚跟，等待着心的袭击。",
            "“米歇尔——！”",
            "美咲松了一口气，刚准备跟着一起挥手谢幕，右腿却在这一刻彻底失去了力气。",
            "肌肉猛地抽紧。",
            "“……！”",
            "散场后台，美咲来到了米歇尔专属房间，摘下头套的那一刻忍不住抖擞了一下。",
            "美咲扶着墙慢慢走出房间，刚走到走廊拐角，小腿又轻轻抽了一下，让她下意识停住脚步。",
            "秋天的夜风吹过公园门口，几个人吵吵闹闹的声音渐渐远去。",
        ]
    )

    result = convert_text(text, CONFIG_DIR)

    assert "弦卷心:大家——！今天也要尽情欢笑哦——！ -id -figureId=kokoro;" in result.script
    assert "弦卷心:米歇尔——！ -id -figureId=kokoro;" in result.script
    assert "奥泽美咲:……！ -id -figureId=misaki;" in result.script
    assert "changeBg:演出、排练/其他演出场地/后台2.png -next;" in result.script
    assert "changeBg:公园/公园1（晚上）.png -next;" in result.script
    assert "changeBg:学校、工作/羽丘/羽丘走廊（白天）.png -next;" not in result.script
    assert "changeBg:公园/公园1（白天）.png -next;" not in result.script
    assert all(item.segment_index is not None for item in result.pending_items)


def test_scene_lock_keeps_background_fixed() -> None:
    text = "\n".join(
        [
            "清晨，立希走进教室。",
            "中午，立希来到中庭。",
        ]
    )

    result = convert_text(text, CONFIG_DIR, scene_lock="排练室")

    assert result.script.count("changeBg:") == 1
    assert result.script.startswith("changeBg:演出、排练/")


def test_segment_scene_lock_changes_background_from_segment() -> None:
    text = "\n".join(
        [
            "清晨，立希走进教室。",
            "傍晚，立希来到排练室。",
        ]
    )

    result = convert_text(text, CONFIG_DIR, segment_scene_locks={1: "排练室"})

    assert "changeBg:学校、工作/花咲川/花咲川教室（白天）.png -next;" in result.script
    assert "changeBg:演出、排练/其他排练场地/排练室4.png -next;" in result.script


def test_figure_control_can_hide_character_figure() -> None:
    result = convert_text("灯：你好", CONFIG_DIR, figure_controls={"tomori": {"visibility": "hide"}})

    assert "灯:你好 -id -figureId=tomori;" in result.script
    assert "changeFigure:tomori/" not in result.script


def test_figure_control_can_force_position() -> None:
    result = convert_text("灯：你好", CONFIG_DIR, figure_controls={"tomori": {"position": "-right"}})

    assert "changeFigure:tomori/036_school_winter-2023model.json -id=tomori -motion=idle01 -expression=default -right -next;" in result.script


def test_global_figure_control_applies_to_all_characters() -> None:
    result = convert_text("灯：你好\n爱音：你好呀", CONFIG_DIR, figure_controls={"__all__": {"visibility": "hide"}})

    assert "灯:你好 -id -figureId=tomori;" in result.script
    assert "爱音:你好呀 -id -figureId=anon;" in result.script
    assert "changeFigure:tomori/" not in result.script
    assert "changeFigure:anon/" not in result.script


def test_model_override_uses_generic_key_when_auto_prefers_31() -> None:
    result = convert_text("立希：测试", CONFIG_DIR, model_overrides={"taki": "casual_summer"})

    assert "changeFigure:taki/040_casual_summer-2023model.json" in result.script


def test_figure_event_override_only_changes_target_figure_line() -> None:
    text = "\n".join(
        [
            "清晨，立希走进教室。",
            "立希：早。",
            "傍晚，立希来到排练室。",
            "立希：午安。",
        ]
    )

    result = convert_text(
        text,
        CONFIG_DIR,
        segment_scene_locks={2: "排练室"},
        figure_event_overrides={
            1: {
                "model_key": "casual_summer",
                "motion": "custom_motion",
                "expression": "smile",
                "position": "-right",
            }
        },
    )

    assert "changeFigure:taki/school_winter-2023/model.json -id=taki" in result.script
    assert "changeFigure:taki/040_casual_summer-2023model.json -id=taki -motion=custom_motion -expression=smile -right -next;" in result.script


def test_figure_event_override_can_use_external_model_path() -> None:
    result = convert_text(
        "灯：你好",
        CONFIG_DIR,
        figure_event_overrides={
            0: {
                "model_path": "户山香澄/casual/idle01_default.png",
                "resource_type": "legacy",
                "source_name": "户山香澄",
                "model_key": "casual",
                "motion": "idle01",
                "expression": "default",
            }
        },
    )

    assert "changeFigure:户山香澄/casual/idle01_default.png -id=tomori -motion=idle01 -expression=default -left -next;" in result.script


def test_convert_text_prefers_external_figure_index_when_available() -> None:
    index = FigureResourceIndex(
        root_dir=ROOT / "dummy_external_figure",
        characters={
            "高松灯": FigureCharacterEntry(
                source_name="高松灯",
                mapped_character_id="tomori",
                mapping_source="manual",
                models={
                    "school_winter-2023": FigureModelEntry(
                        model_key="school_winter-2023",
                        model_path="高松灯/school_winter-2023/model.json",
                        resource_type="live2d_json",
                        character_dir_name="高松灯",
                        motions=["idle01", "wave01"],
                        expressions=["default", "smile"],
                    )
                },
            )
        },
    )

    result = convert_text("灯：你好", CONFIG_DIR, figure_resource_index=index)

    assert "changeFigure:高松灯/school_winter-2023/model.json -id=tomori -motion=idle01 -expression=default -left -next;" in result.script


def test_convert_text_prefers_legacy_model_json_over_other_external_assets() -> None:
    index = FigureResourceIndex(
        root_dir=ROOT / "dummy_external_figure",
        characters={
            "hagumi": FigureCharacterEntry(
                source_name="hagumi",
                mapped_character_id="hagumi",
                mapping_source="auto",
                models={
                    "casual-2023": FigureModelEntry(
                        model_key="casual-2023",
                        model_path="hagumi/013_casual-2023model.json",
                        resource_type="legacy_json",
                        character_dir_name="hagumi",
                        motions=["idle01"],
                        expressions=["default", "smile01"],
                    ),
                    "live2d_texture": FigureModelEntry(
                        model_key="live2d_texture",
                        model_path="hagumi/live2d/chara/013_2018_dog_rip/texture_00.png",
                        resource_type="legacy",
                        character_dir_name="hagumi",
                        motions=["texture"],
                        expressions=["00"],
                    ),
                },
            )
        },
    )

    result = convert_text("育美：你好呀", CONFIG_DIR, figure_resource_index=index)

    assert "changeFigure:hagumi/013_casual-2023model.json -id=hagumi -motion=idle01 -expression=default -left -next;" in result.script


def test_single_character_alias_does_not_match_inside_common_word() -> None:
    config = load_config(CONFIG_DIR)
    mentions = SpeakerResolver(config).find_character_mentions("在学生会室的灯光下，安安静静地落在桌面上。")

    assert "tomori" not in mentions


def test_embedded_quoted_terms_stay_as_narration() -> None:
    segments = parse_text("既然真的会吐花瓣，那目前能参考的也只有这个奇怪的“花吐症”设定了。")

    assert len(segments) == 1
    assert segments[0].kind.value == "narration"
    assert "花吐症" in segments[0].text


def test_narration_mentions_do_not_force_unrelated_figures_on_stage() -> None:
    text = "\n".join(
        [
            "奥泽美咲一边揉着脑袋，一边推开学生会室的门。",
            "今天一整天的课还算能听得下去，心和育美今天也没怎么瞎胡闹添麻烦。",
        ]
    )

    result = convert_text(text, CONFIG_DIR)

    assert "changeFigure:misaki/" in result.script
    assert "changeFigure:kokoro/" not in result.script
    assert "changeFigure:hagumi/" not in result.script


def test_home_scene_detection_prefers_character_room_over_old_school_scene() -> None:
    text = "\n".join(
        [
            "奥泽美咲一边揉着脑袋，一边推开学生会室的门。",
            "被赶回家后，美咲整个人直接倒进床里。",
            "美咲不知道什么时候慢慢睡着了，枕头旁边，几片金色花瓣静静地落在那里。",
        ]
    )

    result = convert_text(text, CONFIG_DIR)

    assert "changeBg:角色生活地点/hello happy world/美咲的房间.png -next;" in result.script
