import sys
import os
from logging import getLogger, StreamHandler, DEBUG
from subprocess import TimeoutExpired
from time import sleep
from selenium import webdriver
from selenium.webdriver.support.expected_conditions import visibility_of_element_located as visible
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.common.exceptions import WebDriverException
from pyvirtualdisplay import Display
import chromedriver_binary
import ffmpeg
import uuid
import boto3
import signal

screen_width = os.getenv('SCREEN_WIDTH', 1920)
screen_height = os.getenv('SCREEN_HEIGHT', 1080)
screen_resolution = f'{screen_width}x{screen_height}'
color_depth = os.getenv('COLOR_DEPTH', 24)
video_bitrate = os.getenv('VIDEO_BITRATE', '4500k')
#video_minrate = os.getenv('VIDEO_MINRATE', '3000k')
#video_maxrate = os.getenv('VIDEO_MAXRATE', '6000k')
#video_bufsize = os.getenv('VIDEO_BUFSIZE', '12000k')
video_framerate = os.getenv('VIDEO_FRAMERATE', 30)
filter_framerate = round(video_framerate / 1.001, 2)
video_gop = video_framerate * 2
audio_codec = os.getenv('AUDIO_CODEC', 'aac')
audio_bitrate = os.getenv('AUDIO_BITRATE', '128k')
audio_samplerate = os.getenv('AUDIO_SAMPLERATE', 44100)
audio_channels = os.getenv('AUDIO_CHANNELS', 2)
audio_delays = os.getenv('AUDIO_DELAYS', '2000')
thread_num = os.getenv('THREAD_NUM', 4)

meeting_pin = os.getenv('MEETING_PIN', None)
if meeting_pin:
    src_url = f'https://app.chime.aws/portal/{meeting_pin}'
else:
    src_url = os.getenv('SRC_URL')
if src_url.startswith('https://app.chime.aws/portal/'):
    is_chime = True
else:
    is_chime = False
dst_url = os.getenv('DST_URL')
if dst_url.startswith('rtmp://'):
    dst_type = 'rtmp'
elif dst_url.startswith('s3://'):
    dst_type = 's3'
    s3_bucket = dst_url.split('/')[2]
    s3_key = '/'.join(dst_url.split('/')[3:])
    output_format = dst_url.split('.')[-1]

tmp_file = f'/tmp/{str(uuid.uuid4())}.mp4'  # for Recording

logger = getLogger(__name__)
handler = StreamHandler()
handler.setLevel(DEBUG)
logger.setLevel(DEBUG)
logger.addHandler(handler)
logger.propagate = False

class GracefulKiller:
    kill_now = False
    def __init__(self, ffmpeg_process):
        self.ffmpeg_process = ffmpeg_process
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self, signum, frame):
        logger.info('Start graceful shutdown process...')
        try:
            logger.info('Stopping ffmpeg process gracefully...')
            self.ffmpeg_process.communicate(str.encode('q'), timeout=20)
            logger.info('Successfully stopped ffmpeg process gracefully.')
        except TimeoutExpired:
            logger.warning('Killing ffmpeg process...')
            ffmpeg_process.terminate()
            logger.warning('Successfully killed ffmpeg process.')
        if dst_type == 's3':
            logger.info('Archive a recording file...')
            client = boto3.client('s3')
            with open(tmp_file, 'rb') as f:
                res = client.put_object(
                    Body=f,
                    Bucket=s3_bucket,
                    Key=s3_key,
                    ContentType='video/mp4')
            logger.info(f'Successfully archived a recording file. [s3://{s3_bucket}/{s3_key}]')
        self.kill_now = True

display = Display(visible=False, size=(screen_width, screen_height), color_depth=color_depth)

options = webdriver.ChromeOptions()
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.add_argument('--autoplay-policy=no-user-gesture-required')
options.add_argument(f'---window-size={screen_width},{screen_height}')
options.add_argument('--start-fullscreen')
options.add_experimental_option("excludeSwitches", ['enable-automation'])

capabilities = DesiredCapabilities.CHROME
capabilities['loggingPrefs'] = { 'browser':'ALL' }


if __name__=='__main__':
    logger.info('Launch a virtual display.')
    display.start()

    driver = webdriver.Chrome(options=options, desired_capabilities=capabilities)
    logger.info(f'Open {src_url} .')
    driver.get(src_url)

    # Move mouse out of the way so it doesn't trigger the "pause" overlay on the video tile
    actions = ActionChains(driver)
    actions.move_by_offset(0, screen_height-1)
    actions.perform()
    
    video_stream = ffmpeg.input(
        f':{display.display}',
        f='x11grab',
        s=screen_resolution,
        r=video_framerate,
        draw_mouse=0,
        thread_queue_size=1024).filter('fps', fps=filter_framerate, round='up')

    audio_stream = ffmpeg.input(
        'default',
        f='pulse',
        ac=2,
        thread_queue_size=1024)

    if dst_type == 'rtmp':
        out = ffmpeg.output(
            video_stream,
            audio_stream,
            dst_url,
            f='flv',
            loglevel='error',
                threads=thread_num,
            vcodec='libx264',
                pix_fmt='yuv420p',
                vprofile='main',
                preset='veryfast',
                x264opts='nal-hrd=cbr:no-scenecut',
                video_bitrate=video_bitrate,
                #minrate=video_minrate,
                #maxrate=video_maxrate,
                #bufsize=video_bufsize,
                g=video_gop,
            audio_sync=100,
            filter_complex=f'adelay=delays={audio_delays}|{audio_delays}',
            acodec='aac',
                audio_bitrate=audio_bitrate,
                ac=audio_channels,
                ar=audio_samplerate,
        )
    elif dst_type == 's3':
        if output_format == 'flac':
            out = ffmpeg.output(
                audio_stream,
                tmp_file,
                f='flac',
                loglevel='error',
                    threads=thread_num,
                filter_complex=f'adelay=delays={audio_delays}|{audio_delays}',
                acodec='flac',
                    sample_fmt='s16',
                    strict='-2',
                    #audio_bitrate=audio_bitrate,
                    ac=audio_channels,
                    ar=audio_samplerate,
            )
        else:
            out = ffmpeg.output(
                video_stream,
                audio_stream,
                tmp_file,
                f=output_format,
                loglevel='error',
                    threads=thread_num,
                vcodec='libx264',
                    pix_fmt='yuv420p',
                    vprofile='main',
                    preset='veryfast',
                    x264opts='nal-hrd=cbr:no-scenecut',
                    video_bitrate=video_bitrate,
                    #minrate=video_minrate,
                    #maxrate=video_maxrate,
                    #bufsize=video_bufsize,
                    g=video_gop,
                audio_sync=100,
                filter_complex=f'adelay=delays={audio_delays}|{audio_delays}',
                acodec=audio_codec,
                    audio_bitrate=audio_bitrate,
                    ac=audio_channels,
                    ar=audio_samplerate,
            )
    out = out.overwrite_output()
    logger.info(out.compile())
    logger.info('Launch ffpmeg process...')
    ffmpeg_process = out.run_async(pipe_stdin=True)

    killer = GracefulKiller(ffmpeg_process)
    while not killer.kill_now:
        # check console log
        for entry in driver.get_log('browser'):
            if entry['level'] == 'WARNING':
                logger.warning(entry)
            else:
                logger.info(entry)
        # check page crash
        try:
            current_url = driver.current_url
            logger.info('Browser is not crashed.')
        except WebDriverException as e:
            logger.error(e)
            driver.get(src_url)
            logger.info('Successfully reloaded the browser.')
            current_url = src_url
        # check chime meeting status
        if is_chime:
            if current_url == 'https://app.chime.aws/portal/ended':
                logger.info('This meeting is ended.')
                killer.exit_gracefully(signal.SIGTERM, None)
            try:
                title = driver.find_element_by_class_name('FullScreenOverlay__title')
            except Exception as e:
                title = None
            if title and title.text == 'Meeting ID not found':
                logger.warning(title.text)
                killer.exit_gracefully(signal.SIGTERM, None)
        sleep(5)

    driver.quit()
    display.stop()
    sys.exit(0)
