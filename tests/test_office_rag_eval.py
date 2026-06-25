from koreanops_rag.office.evaluate_rag import token_f1


def test_token_f1_rewards_supported_overlap():
    assert token_f1("기준금리는 3.5 퍼센트입니다", "기준금리 3.5 퍼센트") > 0.7
