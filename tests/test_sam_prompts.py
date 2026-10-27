"""SAM 3.1 box and point prompts (meta_client): the spec Muse Code builds against.

Docs: https://dev.meta.ai/docs/sam/segmenting, "Prompt with boxes and points"
(read 2026-10-27), and the smoke test in docs/SAM-PROMPTS.md:
- the prompt opens with the frame marker "<0f>" (an image has only frame 0);
- objects are separated by commas; each is our id followed by its tokens:
  at most one box, then its points in the order given;
- box: "<|box;x1=..;y1=..;x2=..;y2=..;w=..;h=..|>", x2 and y2 inclusive;
- point: "<|point;x=..;y=..;w=..;h=..|>"; a negative point has "-" before it;
  only points can be negative;
- w and h are the pixel size of the image sent, the same in every token;
- at most 16 objects, each id once; coordinates are whole pixels inside the
  image (rounded down, as the API does).

Muse Spark localizes in a 0 to 1000 grid of the image it saw, (0, 0) top left
and (1000, 1000) bottom right, and may answer slightly out of range (1001):
grid_box_to_pixels clamps and turns a grid box into an inclusive pixel box.
"""

import pytest

from coresight.meta_client import (
    MAX_SAM_OBJECTS,
    SamObject,
    SamPoint,
    grid_box_to_pixels,
    sam_prompt,
)


def test_the_example_of_the_docs():
    objects = [
        SamObject(1, box=(444, 626, 675, 849)),
        SamObject(2, points=(SamPoint(1430, 700), SamPoint(1300, 450, positive=False))),
    ]
    assert sam_prompt(objects, (1800, 1200)) == (
        "<0f>1<|box;x1=444;y1=626;x2=675;y2=849;w=1800;h=1200|>,"
        "2<|point;x=1430;y=700;w=1800;h=1200|>-<|point;x=1300;y=450;w=1800;h=1200|>"
    )


def test_the_box_prompt_of_the_smoke_test():
    prompt = sam_prompt([SamObject(1, box=(314, 41, 500, 268))], (2500, 278))
    assert prompt == "<0f>1<|box;x1=314;y1=41;x2=500;y2=268;w=2500;h=278|>"


def test_the_point_prompt_of_the_smoke_test():
    points = (SamPoint(722, 161), SamPoint(965, 161, positive=False))
    prompt = sam_prompt([SamObject(2, points=points)], (2500, 278))
    assert prompt == "<0f>2<|point;x=722;y=161;w=2500;h=278|>-<|point;x=965;y=161;w=2500;h=278|>"


def test_a_box_and_its_points_on_one_object_box_first():
    obj = SamObject(0, box=(10, 5, 90, 40), points=(SamPoint(50, 20, positive=False),))
    assert sam_prompt([obj], (100, 50)) == (
        "<0f>0<|box;x1=10;y1=5;x2=90;y2=40;w=100;h=50|>-<|point;x=50;y=20;w=100;h=50|>"
    )


def test_objects_keep_the_order_given():
    objects = [SamObject(7, box=(0, 0, 9, 9)), SamObject(3, box=(10, 0, 19, 9))]
    prompt = sam_prompt(objects, (20, 10))
    assert prompt.startswith("<0f>7<|box;") and ",3<|box;x1=10;" in prompt


def test_float_coordinates_are_rounded_down():
    obj = SamObject(1, box=(10.9, 0.2, 20.99, 9.5), points=(SamPoint(15.7, 4.999),))
    assert sam_prompt([obj], (30, 10)) == (
        "<0f>1<|box;x1=10;y1=0;x2=20;y2=9;w=30;h=10|><|point;x=15;y=4;w=30;h=10|>"
    )


def test_the_last_pixel_is_inside_and_the_size_is_not():
    edge = SamObject(1, box=(0, 0, 99, 49), points=(SamPoint(99, 49),))
    assert "x2=99;y2=49" in sam_prompt([edge], (100, 50))
    with pytest.raises(ValueError):
        sam_prompt([SamObject(1, box=(0, 0, 100, 49))], (100, 50))
    with pytest.raises(ValueError):
        sam_prompt([SamObject(1, points=(SamPoint(10, 50),))], (100, 50))


@pytest.mark.parametrize(
    "box",
    [(-1, 0, 10, 10), (0, -1, 10, 10), (20, 0, 10, 10), (0, 20, 10, 10)],
)
def test_a_box_outside_the_image_or_inverted_is_refused(box):
    with pytest.raises(ValueError):
        sam_prompt([SamObject(1, box=box)], (100, 50))


def test_a_one_pixel_box_is_fine():
    assert "x1=5;y1=5;x2=5;y2=5" in sam_prompt([SamObject(1, box=(5, 5, 5, 5))], (10, 10))


def test_a_negative_point_outside_is_refused_too():
    obj = SamObject(1, points=(SamPoint(1, 1), SamPoint(-1, 1, positive=False)))
    with pytest.raises(ValueError):
        sam_prompt([obj], (10, 10))


def test_sixteen_objects_at_most():
    assert MAX_SAM_OBJECTS == 16
    many = [SamObject(i, box=(i, 0, i, 0)) for i in range(16)]
    assert sam_prompt(many, (16, 1)).count("<|box;") == 16
    with pytest.raises(ValueError, match="16"):
        sam_prompt([*many, SamObject(16, points=(SamPoint(0, 0),))], (17, 1))


def test_no_objects_is_refused():
    with pytest.raises(ValueError):
        sam_prompt([], (10, 10))


def test_an_id_appears_once():
    with pytest.raises(ValueError):
        sam_prompt([SamObject(1, box=(0, 0, 1, 1)), SamObject(1, box=(2, 2, 3, 3))], (10, 10))


def test_an_id_is_a_whole_number_from_zero():
    with pytest.raises(ValueError):
        sam_prompt([SamObject(-1, box=(0, 0, 1, 1))], (10, 10))


def test_an_object_needs_a_box_or_a_positive_point():
    with pytest.raises(ValueError):
        sam_prompt([SamObject(1)], (10, 10))
    with pytest.raises(ValueError):
        sam_prompt([SamObject(1, points=(SamPoint(1, 1, positive=False),))], (10, 10))


def test_a_box_with_only_negative_points_is_fine():
    obj = SamObject(1, box=(0, 0, 9, 9), points=(SamPoint(5, 5, positive=False),))
    assert sam_prompt([obj], (10, 10)).endswith("-<|point;x=5;y=5;w=10;h=10|>")


@pytest.mark.parametrize("size", [(0, 10), (10, 0), (-5, 10), (10.5, 10)])
def test_the_image_size_is_positive_whole_pixels(size):
    with pytest.raises(ValueError):
        sam_prompt([SamObject(1, points=(SamPoint(0, 0),))], size)


def test_grid_corners_are_the_image_corners():
    assert grid_box_to_pixels((0, 0, 1000, 1000), (2500, 278)) == (0, 0, 2499, 277)


def test_grid_box_scales_with_the_image_sent():
    # 250/1000 of 2000 px is pixel 500; 500/1000 of 300 px is pixel 150
    assert grid_box_to_pixels((250, 100, 500, 500), (2000, 300)) == (500, 30, 1000, 150)


def test_grid_values_slightly_out_of_range_are_clamped():
    assert grid_box_to_pixels((-3, -1, 1001, 1004), (100, 50)) == (0, 0, 99, 49)


def test_grid_box_given_backwards_is_put_in_order():
    assert grid_box_to_pixels((500, 800, 100, 200), (1000, 1000)) == (100, 200, 500, 800)


def test_a_grid_box_always_makes_a_valid_prompt():
    for grid in [(0, 0, 1000, 1000), (999, 999, 1000, 1000), (0, 0, 0, 0), (1200, -50, 1300, 2)]:
        box = grid_box_to_pixels(grid, (37, 11))
        sam_prompt([SamObject(1, box=box)], (37, 11))  # never raises
