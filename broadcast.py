import os
import logging
import subprocess
from time import sleep
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support.expected_conditions import visibility_of_element_located as visible
from selenium.webdriver.common.action_chains import ActionChains
from pyvirtualdisplay import Display
import chromedriver_binary
import ffmpeg

screen_width = os.getenv('SCREEN_WIDTH', 1920)
screen_height = os.getenv('SCREEN_HEIGHT', 1080)
screen_resolution = f'{screen_width}x{screen_height}'
color_depth = os.getenv('COLOR_DEPTH', 24)
video_bitrate = os.getenv('VIDEO_BITRATE', '4500k')
video_bufsize = os.getenv('VIDEO_BUFSIZE', '9000k')
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

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

display = Display(visible=False, size=(screen_width, screen_height), color_depth=color_depth)

options = webdriver.ChromeOptions()
options.add_argument('--no-sandbox')
options.add_argument('--autoplay-policy=no-user-gesture-required')
options.add_argument(f'---window-size={screen_width},{screen_height}')
options.add_argument('--start-fullscreen')
options.add_experimental_option("excludeSwitches", ['enable-automation'])


if __name__=='__main__':
    display.start()
    subprocess.Popen('pulseaudio', shell=True, env={'DISPLAY': f':{display.display}'})

    driver = webdriver.Chrome(chrome_options=options)
    driver.get(browser_url)
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
        audio_stream,
        video_stream,
        rtmp_url,
        f='flv',
        vcodec='libx264',
        pix_fmt='yuv420p',
        vprofile='main',
        preset='veryfast',
        x264opts='nal-hrd=cbr:no-scenecut',
        minrate=video_bitrate,
        maxrate=video_bitrate,
        bufsize=video_bufsize,
        r=video_framerate,
        g=video_gop,
        filter_complex='adelay=delays=1000|1000',
        acodec='aac',
        audio_bitrate=audio_bitrate,
        ac=audio_channels,
        ar=audio_samplerate,
    )
    out.run_async(pipe_stdin=True)

    while True:
        if meeting_pin and driver.current_url == 'https://app.chime.aws/portal/ended':
            logger.info('This meeting is ended.')
            break
        else:
            sleep(5)
    driver.quit()
    display.stop()
