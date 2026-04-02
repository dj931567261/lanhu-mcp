"""Tests for design annotation style extraction helpers."""

from lanhu_mcp_server import LanhuExtractor


def test_build_style_spec_preserves_zero_radius():
    style = LanhuExtractor._build_style_spec({"radius": 0})

    assert style["border_radius"] == 0
    assert style["border_radius_raw"] == 0
    assert style["border_radius_detail_raw"] == 0


def test_build_style_spec_keeps_scalar_corner_radius():
    style = LanhuExtractor._build_style_spec({"cornerRadius": 24})

    assert style["border_radius"] == 24
    assert style["border_radius_raw"] == 24
    assert style["border_radius_detail_raw"] == 24


def test_build_style_spec_keeps_per_corner_radius_detail():
    style = LanhuExtractor._build_style_spec(
        {
            "topLeftRadius": 32,
            "topRightRadius": 28,
            "bottomRightRadius": 24,
            "bottomLeftRadius": 20,
        }
    )

    assert style["border_radius"] is None
    assert style["border_radius_raw"] is None
    assert style["border_radius_detail_raw"] == {
        "top_left": 32,
        "top_right": 28,
        "bottom_right": 24,
        "bottom_left": 20,
    }


def test_build_style_spec_reads_nested_style_corner_radius():
    style = LanhuExtractor._build_style_spec(
        {
            "style": {
                "cornerRadius": 18,
            }
        }
    )

    assert style["border_radius"] == 18
    assert style["border_radius_raw"] == 18
    assert style["border_radius_detail_raw"] == 18


def test_build_style_spec_reads_point_corner_radius():
    style = LanhuExtractor._build_style_spec(
        {
            "shapePath": {
                "points": [
                    {"cornerRadius": 12},
                    {"cornerRadius": 12},
                    {"cornerRadius": 12},
                    {"cornerRadius": 12},
                ]
            }
        }
    )

    assert style["border_radius"] == 12
    assert style["border_radius_raw"] == 12
    assert style["border_radius_detail_raw"] == 12


def test_build_style_spec_reads_point_corner_radius_detail():
    style = LanhuExtractor._build_style_spec(
        {
            "shapePath": {
                "points": [
                    {"cornerRadius": 16},
                    {"cornerRadius": 14},
                    {"cornerRadius": 12},
                    {"cornerRadius": 10},
                ]
            }
        }
    )

    assert style["border_radius"] is None
    assert style["border_radius_raw"] is None
    assert style["border_radius_detail_raw"] == {
        "top_left": 16,
        "top_right": 14,
        "bottom_right": 12,
        "bottom_left": 10,
    }


def test_convert_style_spec_to_dp_keeps_raw_radius_detail():
    style = {
        "fills": [],
        "borders": [],
        "shadows": [],
        "border_radius": 24,
        "border_radius_raw": 24,
        "border_radius_detail_raw": {
            "top_left": 32,
            "top_right": 28,
            "bottom_right": 24,
            "bottom_left": 20,
            "all": [12, 16],
        },
    }

    converted = LanhuExtractor._convert_style_spec_to_dp(style)

    assert converted["border_radius"] == 24
    assert converted["border_radius_raw"] == 24
    assert converted["border_radius_detail_raw"] == {
        "top_left": 32,
        "top_right": 28,
        "bottom_right": 24,
        "bottom_left": 20,
        "all": [12, 16],
    }
