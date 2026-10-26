from coresight.meta_client import parse_sam_text


def test_parse_sam_text_reads_box_and_mask_per_record():
    text = (
        "<0f>0<|box;x1=211;y1=228;x2=270;y2=254;w=320;h=334;c=0.91|>"
        "<|mask;x=0;y=0;c=0.91;data=27,60,~abc|>,"
        "3<|box;x1=1;y1=2;x2=30;y2=40;w=320;h=334|><|mask;x=0;y=0;data=39,30,!xyz|>"
    )
    records = parse_sam_text(text)
    assert [r["id"] for r in records] == [0, 3]
    assert records[0]["box"]["x2"] == 270
    assert records[0]["box"]["c"] == 0.91
    assert records[0]["mask"] == "27,60,~abc"
    assert records[1]["mask"] == "39,30,!xyz"


def test_parse_sam_text_payload_with_separator_characters():
    text = (
        "<0f>0<|box;x1=1;y1=2;x2=3;y2=4;w=10;h=10|><|mask;x=0;y=0;data=2,2,~a|>b,c;d|>,"
        "1<|box;x1=5;y1=6;x2=7;y2=8;w=10;h=10|><|mask;x=0;y=0;data=2,2,!z|>\n"
    )
    records = parse_sam_text(text)
    assert [r["mask"] for r in records] == ["2,2,~a|>b,c;d", "2,2,!z"]


def test_parse_sam_text_no_matches():
    assert parse_sam_text("") == []
