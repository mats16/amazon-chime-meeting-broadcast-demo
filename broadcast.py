import sys
import os
import logging
import subprocess
from time import sleep
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support.expected_conditions import visibility_of_element_located as visible
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from pyvirtualdisplay import Display
import chromedriver_binary
import ffmpeg

screen_width = os.getenv('SCREEN_WIDTH', 1920)
screen_height = os.getenv('SCREEN_HEIGHT', 1080)
screen_resolution = f'{screen_width}x{screen_height}'
color_depth = os.getenv('COLOR_DEPTH', 24)
video_bitrate = os.getenv('VIDEO_BITRATE', None)
if video_bitrate:
    video_minrate = video_maxrate = video_bitrate
else:
    video_minrate = os.getenv('VIDEO_MINRATE', '3000k')
    video_maxrate = os.getenv('VIDEO_MAXRATE', '6000k')
video_bufsize = os.getenv('VIDEO_BUFSIZE', '12000k')
video_framerate = os.getenv('VIDEO_FRAMERATE', 30)
video_gop = video_framerate * 2
audio_bitrate = os.getenv('AUDIO_BITRATE', '128k')
audio_samplerate = os.getenv('AUDIO_BITRATE', 44100)
audio_channels = os.getenv('AUDIO_CHANNELS', 2)

rtmp_url = os.getenv('RTMP_URL')
meeting_pin = os.getenv('MEETING_PIN', None)
if meeting_pin:
    browser_url = f'https://app.chime.aws/portal/{meeting_pin}'
else:
    browser_url = os.getenv('BROWSER_URL')
if browser_url.startswith('https://app.chime.aws/portal/'):
    is_chime = True
else:
    is_chime = False

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

display = Display(visible=False, size=(screen_width, screen_height), color_depth=color_depth)

options = webdriver.ChromeOptions()
options.add_argument('--no-sandbox')
options.add_argument('--autoplay-policy=no-user-gesture-required')
options.add_argument(f'---window-size={screen_width},{screen_height}')
options.add_argument('--start-fullscreen')
options.add_experimental_option("excludeSwitches", ['enable-automation'])

capabilities = DesiredCapabilities.CHROME
capabilities['loggingPrefs'] = { 'browser':'ALL' }


if __name__=='__main__':
    subprocess.Popen('pulseaudio', shell=True)
    display.start()

    driver = webdriver.Chrome(chrome_options=options, desired_capabilities=capabilities)
    driver.get(browser_url)

    if is_chime:
        wait = WebDriverWait(driver, 10)
        wait.until(visible((By.ID, 'app')))
        # Move mouse out of the way so it doesn't trigger the "pause" overlay on the video tile
        actions = ActionChains(driver)
        actions.move_to_element(driver.find_element_by_id('app'))
        actions.move_by_offset(screen_width/2, screen_height/2)
        actions.perform()
    
    video_stream = ffmpeg.input(
        f':{display.display}',
        f='x11grab',
        s=screen_resolution,
        r=video_framerate,
        thread_queue_size=1024,
        draw_mouse=0)

    audio_stream = ffmpeg.input(
        'default',
        f='pulse',
        ac=2,
        thread_queue_size=1024)
        
    out = ffmpeg.output(
        video_stream,
        audio_stream,
        rtmp_url,
        f='flv',
        vcodec='libx264',
        pix_fmt='yuv420p',
        vprofile='main',
        preset='veryfast',
        x264opts='nal-hrd=cbr:no-scenecut',
        minrate=video_minrate,
        maxrate=video_maxrate,
        bufsize=video_bufsize,
        r=video_framerate,
        g=video_gop,
        filter_complex='adelay=delays=2000|2000',
        acodec='aac',
        audio_bitrate=audio_bitrate,
        ac=audio_channels,
        ar=audio_samplerate,
    )
    out.run_async(pipe_stdin=True)

    while True:
        if is_chime:
            if driver.current_url == 'https://app.chime.aws/portal/ended':
                logger.info('This meeting is ended.')
                break
            else:
                try:
                    title = driver.find_element_by_class_name('FullScreenOverlay__title')
                except Exception as e:
                    title = None
                if title and title.text == 'Meeting ID not found':
                    logger.info(title.text)
                    break
        sleep(5)
    driver.quit()
    display.stop()
    sys.exit(0)
