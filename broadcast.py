import sys
import os
import logging
import subprocess
from time import sleep
from selenium import webdriver
from selenium.webdriver.support.expected_conditions import visibility_of_element_located as visible
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from pyvirtualdisplay import Display
import chromedriver_binary
import ffmpeg

screen_width = os.getenv('SCREEN_WIDTH', 1920)
screen_height = os.getenv('SCREEN_HEIGHT', 1080)
screen_resolution = f'{screen_width}x{screen_height}'
color_depth = os.getenv('COLOR_DEPTH', 24)
video_bitrate = os.getenv('VIDEO_BITRATE', '4500k')
#video_minrate = os.getenv('VIDEO_MINRATE', '3000k')
#video_maxrate = os.getenv('VIDEO_MAXRATE', '6000k')
#video_bufsize = os.getenv('VIDEO_BUFSIZE', '12000k')
video_framerate = os.getenv('VIDEO_FRAMERATE', 30)
video_gop = video_framerate * 2
audio_bitrate = os.getenv('AUDIO_BITRATE', '128k')
audio_samplerate = os.getenv('AUDIO_BITRATE', 44100)
audio_channels = os.getenv('AUDIO_CHANNELS', 2)
audio_delays = os.getenv('AUDIO_DELAYS', '1800')
thread_num = os.getenv('THREAD_NUM', 4)

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
    display.start()

    driver = webdriver.Chrome(chrome_options=options, desired_capabilities=capabilities)
    driver.get(browser_url)

    # Move mouse out of the way so it doesn't trigger the "pause" overlay on the video tile
    actions = ActionChains(driver)
    actions.move_by_offset(0, screen_height-1)
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
        video_bitrate=video_bitrate,
        #minrate=video_minrate,
        #maxrate=video_maxrate,
        #bufsize=video_bufsize,
        r=video_framerate,
        g=video_gop,
        filter_complex=f'adelay=delays={audio_delays}|{audio_delays}',
        acodec='aac',
        audio_bitrate=audio_bitrate,
        ac=audio_channels,
        ar=audio_samplerate,
        threads=thread_num,
        loglevel='error',
    )
    out.run_async(pipe_stdin=True)

    while True:
        for entry in driver.get_log('browser'):
            logger.info(entry)
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
