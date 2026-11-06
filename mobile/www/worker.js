/* Runs the GeoLab Python engine (Pyodide) off the UI thread. Messages: {id, fn, args} -> {id, ok, result|error}. */
let py = null;
let api = null;

async function boot(base) {
  importScripts(base + "pyodide.js");
  postMessage({ progress: "Starting Python..." });
  py = await loadPyodide({ indexURL: base });
  postMessage({ progress: "Loading numpy and scipy..." });
  await py.loadPackage(["numpy", "scipy"]);
  postMessage({ progress: "Loading the GeoLab engine..." });
  const zip = await (await fetch("geolab.zip")).arrayBuffer();
  py.unpackArchive(zip, "zip", { extractDir: "/home/pyodide/app" });
  py.runPython("import sys; sys.path.insert(0, '/home/pyodide/app')");
  api = py.pyimport("mobile_api");
}

self.onmessage = async (e) => {
  const { id, fn, args, base } = e.data;
  try {
    if (fn === "__boot__") {
      await boot(base);
      postMessage({ id, ok: true, result: api.info() });
      return;
    }
    const f = api[fn];
    if (!f) throw new Error("Unknown function " + fn);
    const result = f(...(args || []));
    postMessage({ id, ok: true, result });
  } catch (err) {
    let msg = String(err && err.message ? err.message : err);
    // keep only the last line of a Python traceback ("ValueError: ...")
    const lines = msg.trim().split("\n").filter(Boolean);
    if (lines.length > 1 && /Traceback/.test(msg)) msg = lines[lines.length - 1];
    msg = msg.replace(/^(ValueError|KeyError|RuntimeError|Exception): /, "");
    postMessage({ id, ok: false, error: msg });
  }
};
