from app.parser.pdf_extractor import reconstruct_tree, content_hash

def fake(lines):
    return {"title":"Test Manual","lines":[{"text":x,"page":1,"font_size":10,"bbox":[0,0,1,1],"kind":"text"} for x in lines]}

def test_duplicate_headings_are_distinct_nodes_with_correct_parents():
    tree=reconstruct_tree(fake(["1 Alpha","1.1 Common","2 Beta","2.1 Common"]))
    common=[n for n in tree if n["heading"].endswith("Common")]
    assert len(common)==2
    assert common[0]["node_index"] != common[1]["node_index"]
    assert tree[common[0]["parent_index"]]["heading"]=="1 Alpha"
    assert tree[common[1]["parent_index"]]["heading"]=="2 Beta"

def test_missing_numbering_level_attaches_to_nearest_existing_prefix():
    tree=reconstruct_tree(fake(["2 Specifications","2.1 General","2.1.1.1 Battery Life"]))
    leaf=next(n for n in tree if n["heading"].endswith("Battery Life"))
    assert tree[leaf["parent_index"]]["heading"]=="2.1 General"

def test_out_of_order_siblings_do_not_become_parent_child():
    tree=reconstruct_tree(fake(["3 Device Operation","3.4 Auto Shutoff","3.3 Result Display"]))
    a=next(n for n in tree if n["heading"].startswith("3.4 "))
    b=next(n for n in tree if n["heading"].startswith("3.3 "))
    assert a["parent_index"] == b["parent_index"]
    assert a["parent_index"] is not None

def test_hash_changes_when_body_changes():
    assert content_hash("4.2 Error Codes","E3 within 2 seconds") != content_hash("4.2 Error Codes","E3 within 1.5 seconds")
