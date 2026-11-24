@echo off
REM Chay camera truc tiep hien thi khung xuong tay va cu chi (khong can websocket, khong can trinh duyet)
cd /d "%~dp0"
python backend\test_camera_gesture.py
pause
