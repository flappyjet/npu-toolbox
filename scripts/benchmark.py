#!/usr/bin/env -S uv run
# /// script
# dependencies = [
#     "ai-edge-litert>=2.1.0",
#     "numpy>=2.4.1",
#     "pillow>=12.1.0",
# ]
# ///
import argparse
import os
import time
import glob
import json
import numpy as np
import ai_edge_litert.interpreter as litert
from PIL import Image
from pathlib import Path
import tomllib

_BASE_DIR = os.environ.get('TOOLBOX_BASE_DIR')
TOOLBOX_BASE_DIR = (Path(_BASE_DIR) if _BASE_DIR else Path(__file__).parent.parent).resolve()
DATA_DIR = TOOLBOX_BASE_DIR / 'data'
MODEL_DIR = TOOLBOX_BASE_DIR / 'models'
PRESETS = {
    "bird": {
        "model": "mobilenet_v2_1.0_224_inat_bird_quant.tflite",
        "labels": "inat_bird_labels.txt",
        "type": "classifier"
    },
    "mobilenet": {
        "model": "mobilenet_v2_1.0_224_quant.tflite",
        "labels": "imagenet_labels.txt",
        "type": "classifier"
    },
    "ssdlite": {
        "model": "ssdlite_mobiledet_coco_qat_postprocess.tflite",
        "labels": "coco_labels.txt",
        "type": "ssdlite"
    }
}
DELEGATE_PATH = None

def get_platform_info():
    try:
        env_path = TOOLBOX_BASE_DIR / "npu_env.toml"
        with open(env_path, "rb") as f:
            data = tomllib.load(f)
            return data
    except (FileNotFoundError, KeyError, Exception):
        return None

def preprocess_image(image_path, target_size):
    img = Image.open(image_path).convert('RGB')
    img = img.resize((target_size[1], target_size[2]), Image.BILINEAR)
    return np.expand_dims(np.array(img, dtype=np.uint8), axis=0)

def load_labels(path):
    if not path or not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f.readlines() if line.strip()]
            
def get_interpreter(model_path, use_npu=False):
    delegates = [litert.load_delegate(DELEGATE_PATH)] if use_npu else []
    interp = litert.Interpreter(model_path=model_path, experimental_delegates=delegates)
    interp.allocate_tensors()
    return interp
    
def extract_results(interp, model_type, labels):
    out = interp.get_output_details()
    
    if model_type == "ssdlite":
        # output: [Boxes, Classes, Scores, Count]
        boxes = interp.get_tensor(out[0]['index'])[0]
        classes = interp.get_tensor(out[1]['index'])[0]
        scores = interp.get_tensor(out[2]['index'])[0]
        
        valid_dets = []
        for i in range(len(scores)):
            if scores[i] > 0.4:  # Confidence
                class_id = int(classes[i])
                label = labels[class_id] if class_id < len(labels) else "--"
                valid_dets.append({
                    "box": boxes[i].tolist(), # [ymin, xmin, ymax, xmax]
                    "class_id": class_id, 
                    "label": label,
                    "score": float(scores[i])
                })
        return {"summary": f"Detected {len(valid_dets)}", "details": valid_dets}
    
    else:
        # output: [1, NumClasses]
        probs = interp.get_tensor(out[0]['index'])[0]
        idx = np.argmax(probs)
        label = f"{labels[idx]}" if idx < len(labels) else "--"
        return {"summary": f"ID:{idx}|{label}", "details": [{"class_id": idx, "label": label, "score": float(probs[idx])}]}


def run_benchmark(model_tag, config, img_list, delegate=None):
    model_path = str(MODEL_DIR / config["model"])
    model_labels = load_labels(str(MODEL_DIR / config["labels"]))
    test_groups = []
    try:
        itp_cpu = get_interpreter(model_path, use_npu=False)
        test_groups.append(("CPU", itp_cpu))
    except Exception as e:
        return {"error": str(e)}

    if delegate:
        try:
            itp_npu = get_interpreter(model_path, use_npu=True)
            test_groups.append(("NPU", itp_npu))
        except Exception as e:
            return {"error": str(e)}
    
    input_idx = itp_cpu.get_input_details()[0]['index']
    target_size = itp_cpu.get_input_details()[0]['shape'][1:3]

    records = []
    for img_path in img_list:
        img_name = os.path.basename(img_path)
        img = Image.open(img_path).convert('RGB').resize((target_size[1], target_size[0]))
        input_data = np.expand_dims(np.array(img, dtype=np.uint8), axis=0)

        for backend, interp in test_groups:
            interp.set_tensor(input_idx, input_data)
            start = time.perf_counter()
            interp.invoke()
            elapsed = (time.perf_counter() - start) * 1000
            
            data = extract_results(interp, model_tag, model_labels)
            records.append({
                "model": model_tag,
                "image": img_name,
                "backend": backend,
                "invoke_ms": elapsed,
                "summary": data["summary"],
                "details": data["details"]
            })
    
    return records

def print_to_console(model_tag, results):
    print(f"\n{'='*80}")
    print(f"Model: {model_tag}")
    print(f"{'Image':<20} | {'Backend':<7} | {'Time (ms)':<10} | {'Result'}")
    print("-" * 80)
    for data in results:
        backend = data["backend"] # "CPU" or "NPU"
        print(f"{data['image']:<20} | {data['backend']:<7} | {data['invoke_ms']:>9.2f} | {data['summary']}")
        print("-" * 80)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog='npu-toolbox benchmark', add_help=True)
    parser.add_argument("--delegate", help="select delegate(*.so)")
    parser.add_argument("--model", choices=["bird", "mobilenet", "ssdlite", "all"], default="all", help="select test models")
    # parser.add_argument("--report", action="store_true", help="generate benchmark report")

    npu_info = get_platform_info()
    if not npu_info:
        print('failed to read npu_env.toml')
    
    if not npu_info.get("libraries", {}).get("no_delegate", 0):
        DELEGATE_PATH = npu_info.get("libraries", {}).get('delegate',None)

    args = parser.parse_args()
    if args.delegate:
        DELEGATE_PATH = args.delegate
    
    if not DELEGATE_PATH:
        print(f"no delegate")
    elif not Path(DELEGATE_PATH).exists():
        print(f"delegate not found {DELEGATE_PATH}")
        DELEGATE_PATH = None

    # scan images from data_dir
    data_dir = str(DATA_DIR)
    valid_exts = ('.jpg', '.jpeg', '.png', '.bmp')
    img_files = sorted([
        os.path.join(data_dir, f) for f in os.listdir(data_dir) 
        if f.lower().endswith(valid_exts)
    ])

    if not img_files:
        print("Please add some images.")
        exit()

    # test model(s) on CPU/NPU
    full_results = []
    targets = [args.model] if args.model != "all" else PRESETS.keys()

    for model_tag in targets:
        conf = PRESETS[model_tag]
        model_path = MODEL_DIR / conf["model"]
        if not model_path.exists():
            print(f"Skip: {str(model_path)} does not exist")
            continue

        res = run_benchmark(model_tag, conf, img_files, DELEGATE_PATH)
        if "error" in res:
            print(f"benchmark fail: {res['error']}")
        else:
            print_to_console(model_tag, res)
            full_results.extend(res)
