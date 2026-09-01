import logging

"""
loggig 초기화 부분입니다.

log level
debug - info - warning - error - critical

사용 방법은
```
import logging

logger = logging.getLogger()
logger.debug('Log level Test')
[26-08-31 15:35:20.568][DEBUG][logger.py::init_logger():78] > Log level Test

logger.info('Log level Test')
[26-08-31 15:33:29.099][INFO][logger.py::init_logger():63] > Log level Test

logger.warning('Log level Test')
[26-08-31 15:33:29.099][WARNING][logger.py::init_logger():64] > Log level Test

logger.error('Log level Test')
[26-08-31 15:33:29.099][ERROR][logger.py::init_logger():65] > Log level Test

logger.critical('Log level Test')
[26-08-31 15:33:29.099][CRITICAL][logger.py::init_logger():66] > Log level Test
```
또는 

```
from logging import getLogger

getLogger().debug(msg)
```

형태로 써도 됩니다.
"""

def init_logger(file_name = 'pet_rec', level = logging.DEBUG):
    
    """
    # params
    * file_name: save text file at dir

            * app/core/config.py - LOGGER_DIR: save directory
            * save_file: LOOGER_DIR/{file_name}_yy-mm-dd_HH:MM:SS.log
    * level: log level

            * write log file at write level > log level

    # log format
    [time][log_level][file::func:line] > msg
    * call logging at func scope

            * [26-08-31 15:15:33.529][INFO][logger.py::init_logger():38] > Start Logger!!!
            
    * call logging at non-func scope

            * [26-08-31 15:19:45.585][INFO][logger.py::<module>():47] > Test Non Func
            
    """

    #현재 시간을 문자열로
    from datetime import datetime
    cur_time = datetime.now().strftime("%y-%m-%d_%H.%M.%S")

    # 인자로 들어온 이름에 시간 + 확장자 붙이기
    file_name = file_name + '_' + cur_time + '.log'
    
    from pathlib import Path
    from app.core.config import LOGGER_DIR

    Path.mkdir(LOGGER_DIR, exist_ok= True)
    
    #basicConfig를 수행하면 root에 해당 파라미터를 적용 됨
    FMT = "[%(asctime)s.%(msecs)03d][%(levelname)s][%(filename)s::%(funcName)s():%(lineno)d] > %(message)s"
    DATEFMT = "%y-%m-%d %H:%M:%S"
    logging.basicConfig(
        filename= LOGGER_DIR / file_name, 
        filemode = 'w',
        format = FMT,
        datefmt = DATEFMT,
        level=level)

    # 인자 없이 호출하면 root logger를 리턴
    logger = logging.getLogger()
    logger.info('Start Logger!!!')

    # logger.debug('Log level Test')
    # logger.info('Log level Test')
    # logger.warning('Log level Test')
    # logger.error('Log level Test')
    # logger.critical('Log level Test')

if __name__ == '__main__':
    init_logger()

# logging.getLogger().info('Test Non Func')