#!/usr/bin/env python3
import sys, os, json, traceback
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from minutes.minio_client import make_minio_client
from minutes.bg_store import update_task_success

TASK_ID='3f5e8b0f-294a-4e10-a1e5-da8694898ed7'
local_path='/app/data/outputs/minutes_20260903145944.txt'

bucket = os.environ.get('MINIO_DEFAULT_BUCKET') or os.environ.get('MINIO_BUCKET') or 'outputs'
object_name = f"minutes/{TASK_ID}/minutes_20260903145944.txt"

out = { 'task_id': TASK_ID, 'local_path': local_path, 'bucket': bucket, 'object_name': object_name }
try:
    client = make_minio_client()
    out['client'] = True
    # ensure bucket
    try:
        out['bucket_exists_before'] = client.bucket_exists(bucket)
    except Exception as e:
        out['bucket_exists_before_error'] = repr(e)
    try:
        client.make_bucket(bucket)
        out['make_bucket'] = 'ok'
    except Exception as e:
        out['make_bucket_error'] = repr(e)
    # upload
    try:
        client.fput_object(bucket, object_name, local_path)
        out['fput_object'] = 'ok'
    except Exception as e:
        out['fput_object_error'] = traceback.format_exc()
    # stat
    try:
        info = client.stat_object(bucket, object_name)
        out['stat'] = { 'size': info.size, 'etag': info.etag }
    except Exception as e:
        out['stat_error'] = traceback.format_exc()
    # list some objects
    try:
        objs = list(client.list_objects(bucket, prefix=f"minutes/{TASK_ID}/", recursive=True))
        out['listed'] = [o.object_name for o in objs]
    except Exception as e:
        out['list_error'] = traceback.format_exc()
    # update DB
    try:
        merged = { 'output_file': local_path, 'minio': { 'bucket': bucket, 'object': object_name } }
        update_task_success(TASK_ID, merged)
        out['db_update'] = 'ok'
    except Exception as e:
        out['db_update_error'] = traceback.format_exc()
except Exception as e:
    out['error'] = traceback.format_exc()

print(json.dumps(out, indent=2, ensure_ascii=False))
