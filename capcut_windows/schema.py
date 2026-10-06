"""Draft material factories adapted from matt-j-penny/capcut-kit.

Upstream commit: 304c125b626cd35843dc0ba723547ee7ff54eee5.
These internal schema constructors perform no filesystem or UI operations.
"""

from typing import Any
import uuid
from pathlib import Path

DRAFT_ROOT = Path()

def uid() -> str:
    return str(uuid.uuid4()).upper()

def video_material(mid: str, path: str | Path, w: int, h: int, dur_us: int, has_audio: bool) -> dict[str, Any]:
    return {
        "id": mid, "unique_id": "", "type": "video", "duration": dur_us,
        "path": str(path), "media_path": "", "local_id": "", "has_audio": has_audio,
        "reverse_path": "", "intensifies_path": "", "reverse_intensifies_path": "",
        "intensifies_audio_path": "", "cartoon_path": "", "width": w, "height": h,
        "category_id": "", "category_name": "", "material_id": "",
        "material_name": Path(path).name, "material_url": "",
        "crop": {"upper_left_x": 0.0, "upper_left_y": 0.0, "upper_right_x": 1.0,
                 "upper_right_y": 0.0, "lower_left_x": 0.0, "lower_left_y": 1.0,
                 "lower_right_x": 1.0, "lower_right_y": 1.0},
        "crop_ratio": "free", "audio_fade": None, "crop_scale": 1.0,
        "extra_type_option": 0,
        "stable": {"stable_level": 0, "matrix_path": "",
                   "time_range": {"start": 0, "duration": 0}},
        "matting": {"flag": 0, "path": "", "interactiveTime": [],
                    "has_use_quick_brush": False, "strokes": [],
                    "has_use_quick_eraser": False, "expansion": 0, "feather": 0,
                    "reverse": False, "custom_matting_id": "",
                    "enable_matting_stroke": False, "is_clould": False,
                    "mask_video_path": "", "cloud_product_fps": 0.0},
        "source": 0, "source_platform": 0, "formula_id": "", "check_flag": 62978047,
        "video_algorithm": {"algorithms": [], "time_range": None, "path": "",
                            "gameplay_configs": [], "ai_in_painting_config": [],
                            "complement_frame_config": None, "motion_blur_config": None,
                            "deflicker": None, "noise_reduction": None,
                            "quality_enhance": None, "super_resolution": None,
                            "ai_background_configs": [], "smart_complement_frame": None,
                            "aigc_generate": None, "aigc_generate_list": [],
                            "mouth_shape_driver": None, "ai_expression_driven": None,
                            "ai_motion_driven": None, "image_interpretation": None,
                            "story_video_modify_video_config": {
                                "task_id": "", "is_overwrite_last_video": False,
                                "tracker_task_id": "", "generate_id": "",
                                "generate_card_id": ""},
                            "skip_algorithm_index": []},
        "is_unified_beauty_mode": False, "is_set_beauty_mode": False,
        "object_locked": None, "smart_motion": None, "multi_camera_info": None,
        "freeze": None, "picture_from": "none", "picture_set_category_id": "",
        "picture_set_category_name": "", "team_id": "", "local_material_id": "",
        "origin_material_id": "", "request_id": "", "has_sound_separated": False,
        "is_text_edit_overdub": False, "is_ai_generate_content": False,
        "aigc_type": "none", "is_copyright": False, "aigc_history_id": "",
        "aigc_item_id": "", "local_material_from": "", "smart_match_info": None,
        "beauty_face_preset_infos": [], "beauty_body_preset_id": "",
        "beauty_face_auto_preset": {"preset_id": "", "name": "", "rate_map": "",
                                    "scene": ""},
        "beauty_face_auto_preset_infos": [], "beauty_body_auto_preset": None,
        "live_photo_timestamp": -1, "live_photo_cover_path": "",
        "content_feature_info": None, "corner_pin": None, "surface_trackings": [],
        "video_mask_stroke": {"resource_id": "", "path": "", "type": "", "color": "",
                              "size": 0.0, "alpha": 0.0, "distance": 0.0,
                              "texture": 0.0, "horizontal_shift": 0.0,
                              "vertical_shift": 0.0},
        "video_mask_shadow": {"resource_id": "", "path": "", "color": "",
                              "alpha": 0.0, "blur": 0.0, "distance": 0.0,
                              "angle": 0.0},
    }

def segment(mid: str, src_start: int, dur: int, tgt_start: int, refs: list[str]) -> dict[str, Any]:
    return {
        "id": uid(),
        "source_timerange": {"start": src_start, "duration": dur},
        "target_timerange": {"start": tgt_start, "duration": dur},
        "render_timerange": {"start": 0, "duration": 0},
        "desc": "", "state": 0, "speed": 1.0, "is_loop": False,
        "is_tone_modify": False, "reverse": False, "intensifies_audio": False,
        "cartoon": False, "volume": 1.0, "last_nonzero_volume": 1.0,
        "clip": {"scale": {"x": 1.0, "y": 1.0}, "rotation": 0.0,
                 "transform": {"x": 0.0, "y": 0.0},
                 "flip": {"vertical": False, "horizontal": False}, "alpha": 1.0},
        "uniform_scale": {"on": True, "value": 1.0},
        "material_id": mid, "extra_material_refs": refs, "render_index": 0,
        "keyframe_refs": [], "enable_lut": True, "enable_adjust": True,
        "enable_hsl": False, "visible": True, "group_id": "",
        "enable_color_curves": True, "enable_hsl_curves": True,
        "track_render_index": 0,
        "hdr_settings": {"mode": 1, "intensity": 1.0, "nits": 1000},
        "enable_color_wheels": True, "track_attribute": 0, "is_placeholder": False,
        "template_id": "", "enable_smart_color_adjust": False,
        "template_scene": "default", "common_keyframes": [], "caption_info": None,
        "responsive_layout": {"enable": False, "target_follow": "",
                              "size_layout": 0, "horizontal_pos_layout": 0,
                              "vertical_pos_layout": 0},
        "enable_color_match_adjust": False, "enable_color_correct_adjust": False,
        "enable_adjust_mask": False, "raw_segment_id": "", "lyric_keyframes": None,
        "enable_video_mask": True, "digital_human_template_group_id": "",
        "color_correct_alg_result": "", "source": "segmentsourcenormal",
        "enable_mask_stroke": False, "enable_mask_shadow": False,
        "enable_color_adjust_pro": False,
    }

def segment_extras(materials: dict[str, list[dict[str, Any]]]) -> list[str]:
    """Per-segment helper materials, the six-ref set CapCut itself writes."""
    ids = []
    for cat, entry in [
        ("speeds", {"type": "speed", "mode": 0, "speed": 1.0, "curve_speed": None}),
        ("placeholder_infos", {"type": "placeholder_info", "meta_type": "none",
                               "res_path": "", "res_text": "", "error_path": "",
                               "error_text": ""}),
        ("canvases", {"type": "canvas_color", "color": "", "blur": 0.0, "image": "",
                      "album_image": "", "image_id": "", "image_name": "",
                      "source_platform": 0, "team_id": ""}),
        ("sound_channel_mappings", {"type": "", "audio_channel_mapping": 0,
                                    "is_config_open": False}),
        ("material_colors", {"is_color_clip": False, "is_gradient": False,
                             "solid_color": "", "gradient_colors": [],
                             "gradient_percents": [], "gradient_angle": 90.0,
                             "width": 0.0, "height": 0.0}),
        ("vocal_separations", {"type": "vocal_separation", "choice": 0,
                               "removed_sounds": [], "time_range": None,
                               "production_path": "", "final_algorithm": "",
                               "enter_from": ""}),
    ]:
        eid = uid()
        materials[cat].append({"id": eid, **entry})
        ids.append(eid)
    return ids

EMPTY_MATERIAL_CATS: list[str] = [
    "flowers", "tail_leaders", "audios", "images", "texts", "effects", "stickers",
    "transitions", "audio_effects", "audio_fades", "beats", "material_animations",
    "placeholders", "common_mask", "chromas", "text_templates", "realtime_denoises",
    "audio_pannings", "audio_pitch_shifts", "video_trackings", "hsl", "drafts",
    "color_curves", "hsl_curves", "primary_color_wheels", "log_color_wheels",
    "video_effects", "ai_text_effects", "audio_balances", "handwrites",
    "manual_deformations", "manual_beautys", "plugin_effects", "green_screens",
    "shapes", "digital_humans", "digital_human_model_dressing", "smart_crops",
    "ai_translates", "audio_track_indexes", "loudnesses", "vocal_beautifys",
    "smart_relights", "time_marks", "multi_language_refs", "video_shadows",
    "video_strokes", "video_radius", "videos", "canvases", "speeds",
    "placeholder_infos", "sound_channel_mappings", "material_colors",
    "vocal_separations",
]

def build_draft(name: str, raw_path: str | Path, cuts: dict[str, Any], canvas_w: int, canvas_h: int, media: tuple[int, int, int, bool], plat: dict[str, Any]) -> tuple[dict[str, Any], int, int, int]:
    w, h, raw_dur_us, has_audio = media
    materials = {cat: [] for cat in EMPTY_MATERIAL_CATS}
    mid = uid()
    materials["videos"].append(video_material(mid, raw_path, w, h, raw_dur_us, has_audio))

    segments = []
    cursor = 0
    for s in cuts["segments"]:
        src = round(s["start"] * 1e6)
        dur = round((s["end"] - s["start"]) * 1e6)
        segments.append(segment(mid, src, dur, cursor, segment_extras(materials)))
        cursor += dur

    return {
        "id": uid(), "version": 360000, "new_version": "175.0.0", "name": "",
        "duration": cursor, "create_time": 0, "update_time": 0, "fps": 30.0,
        "is_drop_frame_timecode": False, "color_space": 0,
        "config": {"video_mute": False, "record_audio_last_index": 1,
                   "extract_audio_last_index": 1, "original_sound_last_index": 1,
                   "subtitle_recognition_id": "", "subtitle_taskinfo": [],
                   "lyrics_recognition_id": "", "lyrics_taskinfo": [],
                   "subtitle_sync": True, "lyrics_sync": True,
                   "voice_change_sync": False, "sticker_max_index": 1,
                   "adjust_max_index": 1, "material_save_mode": 0,
                   "export_range": None, "maintrack_adsorb": True,
                   "combination_max_index": 1, "attachment_info": [],
                   "zoom_info_params": None, "system_font_list": [],
                   "multi_language_mode": "none", "multi_language_main": "none",
                   "multi_language_current": "none", "multi_language_list": [],
                   "subtitle_keywords_config": None, "use_float_render": False},
        "canvas_config": {"ratio": "original", "width": canvas_w,
                          "height": canvas_h, "background": None},
        "tracks": [{"id": uid(), "type": "video", "segments": segments,
                    "flag": 0, "attribute": 0, "name": "", "is_default_name": True}],
        "group_container": None, "materials": materials,
        "keyframes": {"videos": [], "audios": [], "texts": [], "stickers": [],
                      "filters": [], "adjusts": [], "handwrites": [], "effects": []},
        "keyframe_graph_list": [], "platform": plat,
        "last_modified_platform": plat, "mutable_config": None, "cover": None,
        "retouch_cover": None, "extra_info": None, "relationships": [],
        "mixed_track_mode_on": False, "render_index_track_mode_on": True,
        "free_render_index_mode_on": False, "static_cover_image_path": "",
        "source": "default", "time_marks": None, "path": "", "lyrics_effects": [],
        "uneven_animation_template_info": {"composition": "", "content": "",
                                           "order": "", "sub_template_info_list": []},
        "draft_type": "video",
        "smart_ads_info": {"page_from": "", "routine": "", "draft_url": ""},
    }, raw_dur_us, w, h

def meta_entry(name: str, folder: Path, draft_id: str, raw_path: Path, raw_dur_us: int, w: int, h: int, total_us: int, now_us: int) -> dict[str, Any]:
    now_s = now_us // 1_000_000
    return {
        "cloud_draft_cover": False, "cloud_draft_sync": False,
        "cloud_package_completed_time": "", "draft_cloud_capcut_purchase_info": "",
        "draft_cloud_last_action_download": False, "draft_cloud_package_type": "",
        "draft_cloud_purchase_info": "", "draft_cloud_template_id": "",
        "draft_cloud_tutorial_info": "", "draft_cloud_videocut_purchase_info": "",
        "draft_cover": "draft_cover.jpg", "draft_deeplink_url": "",
        "draft_enterprise_info": {"draft_enterprise_extra": "",
                                  "draft_enterprise_id": "",
                                  "draft_enterprise_name": "",
                                  "enterprise_material": []},
        "draft_fold_path": str(folder), "draft_id": draft_id,
        "draft_is_ae_produce": False, "draft_is_ai_packaging_used": False,
        "draft_is_ai_shorts": False, "draft_is_ai_translate": False,
        "draft_is_article_video_draft": False, "draft_is_cloud_temp_draft": False,
        "draft_is_from_deeplink": "false", "draft_is_invisible": False,
        "draft_is_pippit_draft": False, "draft_is_web_article_video": False,
        "draft_materials": [
            {"type": 0, "value": [{
                "ai_group_type": "", "create_time": now_s, "duration": raw_dur_us,
                "enter_from": 0, "extra_info": Path(raw_path).name,
                "file_Path": str(raw_path), "height": h,
                "id": str(uuid.uuid4()), "import_time": now_s,
                "import_time_ms": now_us, "item_source": 1, "md5": "",
                "metetype": "video",
                "roughcut_time_range": {"duration": raw_dur_us, "start": 0},
                "sub_time_range": {"duration": -1, "start": -1},
                "type": 0, "width": w}]},
            {"type": 1, "value": []}, {"type": 2, "value": []},
            {"type": 3, "value": []}, {"type": 6, "value": []},
            {"type": 7, "value": []},
        ],
        "draft_materials_copied_info": [], "draft_name": name,
        "draft_need_rename_folder": False, "draft_new_version": "",
        "draft_removable_storage_device": "", "draft_root_path": str(DRAFT_ROOT),
        "draft_segment_extra_info": [], "draft_timeline_materials_size_": 0,
        "draft_type": "", "draft_web_article_video_enter_from": "",
        "pippit_avatar_url": "", "pippit_extra_info": "", "pippit_id": "",
        "pippit_user_name": "", "tm_draft_cloud_completed": "",
        "tm_draft_cloud_entry_id": -1, "tm_draft_cloud_modified": 0,
        "tm_draft_cloud_parent_entry_id": -1, "tm_draft_cloud_space_id": -1,
        "tm_draft_cloud_user_id": -1, "tm_draft_create": now_us,
        "tm_draft_modified": now_us, "tm_draft_removed": 0,
        "tm_duration": total_us,
    }

def registry_entry(name: str, folder: Path, draft_id: str, total_us: int, now_us: int) -> dict[str, Any]:
    return {
        "cloud_draft_cover": False, "cloud_draft_sync": False,
        "draft_cloud_last_action_download": False, "draft_cloud_purchase_info": "",
        "draft_cloud_template_id": "", "draft_cloud_tutorial_info": "",
        "draft_cloud_videocut_purchase_info": "",
        "draft_cover": str(folder / "draft_cover.jpg"),
        "draft_fold_path": str(folder), "draft_id": draft_id,
        "draft_is_ai_shorts": False, "draft_is_cloud_temp_draft": False,
        "draft_is_invisible": False, "draft_is_pippit_draft": False,
        "draft_is_web_article_video": False,
        "draft_json_file": str(folder / "draft_content.json"), "draft_name": name,
        "draft_new_version": "", "draft_root_path": str(DRAFT_ROOT),
        "draft_timeline_materials_size": 0, "draft_type": "",
        "draft_web_article_video_enter_from": "", "pippit_avatar_url": "",
        "pippit_extra_info": "", "pippit_id": "", "pippit_user_name": "",
        "streaming_edit_draft_ready": True, "tm_draft_cloud_completed": "",
        "tm_draft_cloud_entry_id": -1, "tm_draft_cloud_modified": 0,
        "tm_draft_cloud_parent_entry_id": -1, "tm_draft_cloud_space_id": -1,
        "tm_draft_cloud_user_id": -1, "tm_draft_create": now_us,
        "tm_draft_modified": now_us, "tm_draft_removed": 0,
        "tm_duration": total_us,
    }
