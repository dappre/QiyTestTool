set FLASK_APP=QiyTestTool\site\flask_app.py
set TARGET=dev2

REM Uncomment the next line if the URLLIB has been fixed as specified in https://github.com/psf/requests/issues/4248#issuecomment-429188281:
REM set QTT_URLLIB_FIXED=TRUE

python -m flask run
