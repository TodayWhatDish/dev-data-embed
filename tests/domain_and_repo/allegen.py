import logging

from app.app_logger.logger import init_logger
from app.domain.common import CommonMgr
from app.repositories.common import get_allgens


def print_allerge_child(child, parent_allergen : str | None = None, tab_cnt = 0):
    """
    # summary
    재귀 함수를 통해, 자식들을 순회하고 모든 자식을 출력
    """
    if parent_allergen:
        logger.info("\t"*tab_cnt + f"{parent_allergen}")

    for c in child:
        print_allerge_child(c["children"], c["name_ko"], tab_cnt+1)

def print_allerge_parent(allergen_hirarchy, allergen_id : int, tab_cnt = 0):
    """
    # summary
        재귀 함수를 통해, 부모들을 출력
    """
    logger.info("\t" * tab_cnt + f"{allergen_hirarchy[allergen_id]["name_ko"]}")
    if allergen_hirarchy[allergen_id]["parent_id"]:
        print_allerge_parent(allergen_hirarchy, allergen_hirarchy[allergen_id]["parent_id"], tab_cnt+1)

def get_parents(allergen_hirarchy, allergen_id):
    """
    # summary
    기준 id로부터 부모로 가는 id들을 반환
    재귀 함수
    """
    ret_val = []
    ret_val.append(allergen_id)
    if allergen_hirarchy[allergen_id]["parent_id"]:
        ret_val = ret_val + get_parents(allergen_hirarchy, allergen_hirarchy[allergen_id]["parent_id"])
    return ret_val

logger = logging.getLogger()


if __name__ == '__main__':
    init_logger('test_allegen')
    mgr = CommonMgr.get_inst()
    
    mgr.set_allergen_info(get_allgens())

    root = mgr.get_allergen()
    for r in root:
        print_allerge_child(r["children"], r["name_ko"], 0)


    logger.info("#"*20)
    select_allergen1 = mgr.get_allergen(3)
    logger.info("select allergen1")
    print_allerge_child(select_allergen1["children"], select_allergen1["name_ko"], 0)
    logger.info("#"*20)

    select_allergen2 = mgr.get_allergen(5)
    logger.info("select allergen2")
    print_allerge_child(select_allergen2["children"], select_allergen2["name_ko"], 0)
    logger.info("#"*20)


    logger.info("reverse iterate")
    allergen_hirarchy = mgr.get_all_allergen_hierarchy()
    print_allerge_parent(allergen_hirarchy, 7) #11번 알러지의 부모들을 출력
    to_par_ids = get_parents(allergen_hirarchy, 7)
    tt  = []
    for id in to_par_ids:
        tt.append(allergen_hirarchy[id]["name_ko"])
    logger.info(tt)
    logger.info("#"*20)

    select_allergen3 = mgr.get_allergen(500)
    logger.info("존재하지 않는 알러지 id - select allergen4")
    if not select_allergen3:
        logger.info("None!!!")
    else:
        raise ValueError(select_allergen3)
    logger.info("#"*20)
    
    logger.info('ok')

"""
단백질
        육류
                가금류
                        닭고기
                        오리
                        칠면조
                적색육
                        소고기
                        돼지고기
                        양고기
        어류
                연어
                참치
                대구
        갑각류
                새우
                게
                홍합
        유제품
                우유
                치즈
                요거트
        난류
                계란
        곤충단백
곡물
        글루텐곡물
                밀
                보리
                호밀
        무글루텐곡물
                옥수수
                쌀
                귀리
                수수
콩류
        대두
        완두
        병아리콩
견과류
        땅콩
채소
        감자
        고구마
        도라지
        더덕
첨가물
        인공색소
        인공보존료
"""