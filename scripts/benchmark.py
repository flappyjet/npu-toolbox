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
import http.server
import socketserver

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
        label = f"{labels[idx]}" if int(idx) < len(labels) else "--"
        return {"summary": f"ID:{idx}|{label}", "details": [{"class_id": int(idx), "label": label}]}


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

def save_as_html(all_data):
    json_data = json.dumps(all_data, indent=2)
    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8"><title>NPU Benchmark</title>
        <style>
            body { font-family: -apple-system, system-ui, sans-serif; background: #f0f2f5; padding: 30px; color: #333; }
            h1 { text-align: center; color: #1a73e8; margin-bottom: 40px; }
            
            .model-section { background: #fff; border-radius: 12px; padding: 25px; margin-bottom: 50px; shadow: 0 4px 15px rgba(0,0,0,0.08); }
            .model-header { border-left: 5px solid #1a73e8; padding-left: 15px; margin-bottom: 25px; }
            .model-header h2 { margin: 0; text-transform: uppercase; letter-spacing: 1px; }

            .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 10px; }

            .card { background: #fafafa; border: 1px solid #eee; border-radius: 8px; overflow: hidden; display: flex; flex-direction: column; }
            .img-name { font-weight: bold; font-size: 14px; padding: 5px 0; text-align:center; }
            .img-wrap { position: relative; width: 100%; background: #000; }
            .img-wrap img { width: 100%; height: 100%; }
            
            .box { position: absolute; border: 2px solid #00ff00; background: rgba(0,255,0,0.1); pointer-events: none; }
            .label-tag { position: absolute; top: -16px; left: -2px; background: #00ff00; color: #000; font-size: 9px; padding: 0 3px; font-weight: bold; }
            
            .content { padding: 15px; flex-grow: 1; display: flex; flex-direction: column; justify-content: space-evenly; }
           
            .backend-info { margin-bottom: 10px; }
            .badge { display: inline-block; padding: 2px 6px; border-radius: 3px; font-size: 11px; font-weight: bold; margin-bottom: 4px; }
            .cpu-badge { background: #6c757d; color: white; }
            .npu-badge { background: #28a745; color: white; }
            
            .stat-line { font-size: 13px; line-height: 1.4; }
            .ms-val { font-family: monospace; font-weight: bold; color: #d93025; }
            .res-val { color: #555; font-style: italic; }
        </style>
    </head>
    <body>
        <h1>NPU benchmark</h1>
        <div id="report-root"></div>

        <script>
            const flatData = __JSON_DATA__["data"];
            const root = document.getElementById('report-root');

            const grouped = flatData.reduce((acc, item) => {
                if (!acc[item.model]) acc[item.model] = {};
                if (!acc[item.model][item.image]) acc[item.model][item.image] = {};
                acc[item.model][item.image][item.backend] = item;
                return acc;
            }, {});

            for (const [modelName, images] of Object.entries(grouped)) {
                const section = document.createElement('div');
                section.className = 'model-section';
                section.innerHTML = `<div class="model-header"><h2>Model: ${modelName}</h2></div>`;
                
                const grid = document.createElement('div');
                grid.className = 'grid';

                for (const [imgName, backends] of Object.entries(images)) {
                    const card = document.createElement('div');
                    card.className = 'card';
                    
                    const npuData = backends['NPU'];
                    const cpuData = backends['CPU'];

                    // object detection
                    let boxesHtml = '';
                    if (npuData && npuData.details) {
                        npuData.details.forEach(d => {
                            if (d.box) {
                                const [y1, x1, y2, x2] = d.box;
                                boxesHtml += `<div class="box" style="top:${y1*100}%; left:${x1*100}%; width:${(x2-x1)*100}%; height:${(y2-y1)*100}%;">
                                    <span class="label-tag">${d.label}</span>
                                </div>`;
                            }
                        });
                    }

                    card.innerHTML = `
                        <div class="img-name">${imgName}</div>
                        <div class="img-wrap">
                            <img src="data/${imgName}">
                            ${boxesHtml}
                        </div>
                        <div class="content">
                            <div class="backend-info">
                                <span class="badge cpu-badge">CPU</span>
                                <div class="stat-line">invoke time: <span class="ms-val">${cpuData ? cpuData.invoke_ms.toFixed(2) : 'N/A'} ms</span></div>
                                <div class="stat-line">result: <span class="res-val">${cpuData ? cpuData.summary : '-'}</span></div>
                            </div>
                            
                            <hr style="border:0; border-top:1px dashed #ccc; margin: 10px 0;">

                            <div class="backend-info">
                                <span class="badge npu-badge">NPU</span>
                                <div class="stat-line">invoke time: <span class="ms-val">${npuData ? npuData.invoke_ms.toFixed(2) : 'N/A'} ms</span></div>
                                <div class="stat-line">result: <span class="res-val">${npuData ? npuData.summary : '-'}</span></div>
                            </div>
                        </div>
                    `;
                    grid.appendChild(card);
                }
                section.appendChild(grid);
                root.appendChild(section);
            }
        </script>
    </body>
    </html>
    """.replace("__JSON_DATA__", json_data)
    with open(TOOLBOX_BASE_DIR / "report.html", "w", encoding="utf-8") as f:
        f.write(html_template)
    print("\nBenchmark finish.")

class CustomHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(TOOLBOX_BASE_DIR), **kwargs)
    def do_GET(self):
        if self.path == '/':
            self.path = '/report.html'
        return super().do_GET()

def http_serve(PORT=8000):
    Handler = CustomHTTPRequestHandler
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"Access report at 0.0.0.0 port {PORT} (http://your-ip:{PORT}/) ...")
        print("Press Ctrl+C to stop HTTP server")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nHTTP server stopped.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog='npu-toolbox benchmark', add_help=True)
    parser.add_argument("--delegate", help="select delegate(*.so)")
    parser.add_argument("--model", choices=["bird", "mobilenet", "ssdlite", "all"], default="all", help="select test models")
    parser.add_argument("--report", metavar='PORT', nargs='?', const=8000, type=int, help="view benchmark report, default PORT=8000")

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

    if args.report:
        save_as_html({"data": full_results})
        http_serve(args.report)