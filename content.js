console.log("VeritAI content script loaded");

const API_URL = "http://localhost:8080/api/detections";
const BUTTON_CLASS = "veritai-check-btn";
const BUTTON_IDLE_LABEL = "🔍";
const BUTTON_BUSY_LABEL = "⏳";

let isProcessing = false;
let attachQueued = false;

function isVisibleMedia(media) {
    const rect = media.getBoundingClientRect();
    return (
        rect.width >= 80 &&
        rect.height >= 80 &&
        rect.bottom > 0 &&
        rect.right > 0 &&
        rect.top < window.innerHeight &&
        rect.left < window.innerWidth
    );
}

function ensureWrapper(media) {
    const parent = media.parentElement;
    if (!parent) {
        return null;
    }

    const style = window.getComputedStyle(parent);
    if (style.position === "static") {
        parent.style.position = "relative";
    }

    return parent;
}

function createButton(media) {
    const btn = document.createElement("button");
    btn.innerText = BUTTON_IDLE_LABEL;
    btn.className = BUTTON_CLASS;
    btn.title = "VeritAI analyze";
    btn.setAttribute("aria-label", "VeritAI analyze");
    btn.style.cssText = `
        position: absolute;
        top: 10px;
        left: 10px;
        z-index: 2147483647;
        width: 38px;
        height: 38px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        padding: 0;
        background-color: #e74c3c;
        color: white;
        border: 2px solid white;
        border-radius: 999px;
        cursor: pointer;
        font-weight: bold;
        font-size: 16px;
        box-shadow: 0 2px 5px rgba(0, 0, 0, 0.3);
    `;

    btn.addEventListener("click", async (event) => {
        event.preventDefault();
        event.stopPropagation();

        if (isProcessing) {
            alert("Another analysis is already in progress.");
            return;
        }

        isProcessing = true;
        btn.innerText = BUTTON_BUSY_LABEL;
        btn.disabled = true;

        try {
            let blob;
            if (media.tagName === "VIDEO") {
                blob = await captureVideoBlob(media);
                await sendToBackend(blob, "video_frame");
            } else if (media.tagName === "IMG") {
                blob = await captureImageBlob(media.currentSrc || media.src);
                await sendToBackend(blob, "image");
            }
        } catch (error) {
            console.error("Media analysis failed:", error);
            const message = error?.message || String(error);
            if (message.includes("Extension context invalidated")) {
                alert("The extension was reloaded. Refresh the page and try again.");
            } else {
                alert(`Error: ${message}`);
            }
        } finally {
            btn.innerText = BUTTON_IDLE_LABEL;
            btn.disabled = false;
            isProcessing = false;
        }
    });

    return btn;
}

function attachButtons() {
    const mediaList = document.querySelectorAll("video, img");

    mediaList.forEach((media) => {
        if (!media.isConnected) {
            return;
        }
        if (!(media instanceof HTMLImageElement || media instanceof HTMLVideoElement)) {
            return;
        }
        if (!isVisibleMedia(media)) {
            return;
        }

        const wrapper = ensureWrapper(media);
        if (!wrapper) {
            return;
        }
        if (wrapper.querySelector(`:scope > .${BUTTON_CLASS}`)) {
            return;
        }

        if (media.tagName === "IMG" && !media.currentSrc && !media.src) {
            return;
        }

        wrapper.appendChild(createButton(media));
    });
}

function scheduleAttachButtons() {
    if (attachQueued) {
        return;
    }
    attachQueued = true;
    window.requestAnimationFrame(() => {
        attachQueued = false;
        attachButtons();
    });
}

async function captureVideoBlob(video) {
    if (!video) {
        throw new Error("Video element not found.");
    }

    const rect = video.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) {
        throw new Error("Video element has zero size.");
    }

    return new Promise((resolve, reject) => {
        chrome.runtime.sendMessage({ action: "capture_tab" }, (response) => {
            if (chrome.runtime.lastError) {
                reject(new Error(chrome.runtime.lastError.message));
                return;
            }
            if (!response || response.error || !response.dataUrl) {
                reject(new Error(response?.error || "No capture data returned."));
                return;
            }

            const fullImage = new Image();
            fullImage.onload = () => {
                try {
                    const canvas = document.createElement("canvas");
                    const ctx = canvas.getContext("2d");
                    if (!ctx) {
                        reject(new Error("Canvas context creation failed."));
                        return;
                    }

                    const dpr = window.devicePixelRatio || 1;
                    const offsetX = Math.floor((rect.left + window.scrollX) * dpr);
                    const offsetY = Math.floor((rect.top + window.scrollY) * dpr);

                    canvas.width = Math.floor(rect.width * dpr);
                    canvas.height = Math.floor(rect.height * dpr);

                    ctx.drawImage(
                        fullImage,
                        offsetX,
                        offsetY,
                        canvas.width,
                        canvas.height,
                        0,
                        0,
                        canvas.width,
                        canvas.height
                    );

                    canvas.toBlob((blob) => {
                        if (!blob) {
                            reject(new Error("Failed to generate video frame blob."));
                            return;
                        }
                        resolve(blob);
                    }, "image/jpeg", 0.9);
                } catch (error) {
                    reject(error);
                }
            };
            fullImage.onerror = () => reject(new Error("Failed to load captured tab image."));
            fullImage.src = response.dataUrl;
        });
    });
}

async function captureImageBlob(url) {
    if (!url) {
        throw new Error("Image URL is missing.");
    }

    return new Promise((resolve, reject) => {
        const img = new Image();
        img.crossOrigin = "anonymous";
        img.referrerPolicy = "no-referrer";

        img.onload = () => {
            try {
                const canvas = document.createElement("canvas");
                const ctx = canvas.getContext("2d");
                if (!ctx) {
                    reject(new Error("Canvas context creation failed."));
                    return;
                }

                canvas.width = img.naturalWidth || img.width;
                canvas.height = img.naturalHeight || img.height;

                if (canvas.width === 0 || canvas.height === 0) {
                    reject(new Error("Image size is zero."));
                    return;
                }

                ctx.drawImage(img, 0, 0);
                canvas.toBlob((blob) => {
                    if (!blob) {
                        reject(new Error("Failed to generate image blob."));
                        return;
                    }
                    resolve(blob);
                }, "image/jpeg", 0.9);
            } catch (error) {
                reject(error);
            }
        };

        img.onerror = () => reject(new Error("Failed to load image."));
        img.src = url;
    });
}

function buildFaceSummary(faces) {
    if (!faces.length) {
        return "\n\nNo faces were detected. Try an image with a larger or clearer face.";
    }

    return "\n\n" + faces.slice(0, 3).map((face, index) => {
        const bbox = face?.bbox || {};
        const quality = face?.quality || {};
        const detectionConfidence = (face?.detectionConfidence ?? face?.score ?? 0) * 100;
        const qualityScore = (quality?.score ?? 0) * 100;

        return [
            `[Face ${index + 1}]`,
            `Position: (${bbox.x ?? "?"}, ${bbox.y ?? "?"}, ${bbox.w ?? "?"}x${bbox.h ?? "?"})`,
            `Type: ${face?.faceMode || "unknown"}`,
            `Detection confidence: ${detectionConfidence.toFixed(1)}%`,
            `Quality: ${quality?.label || "unknown"} (${qualityScore.toFixed(1)}%)`,
        ].join("\n");
    }).join("\n\n");
}

async function sendToBackend(blob, mediaType) {
    const formData = new FormData();
    formData.append("file", blob, "capture.jpg");
    formData.append("sourceUrl", window.location.href);
    formData.append("mediaType", mediaType);
    formData.append("clientType", "chrome-extension");

    const response = await fetch(API_URL, {
        method: "POST",
        body: formData,
    });

    if (!response.ok) {
        throw new Error(`Server response error: ${response.status} / ${await response.text()}`);
    }

    const data = await response.json();
    if (!data || data.status !== "DONE" || !data.result) {
        throw new Error(data?.message || "Analysis did not complete successfully.");
    }

    const result = data.result;
    const confidence = ((result.confidence || 0) * 100).toFixed(2);
    const faces = Array.isArray(result.faces) ? result.faces : [];

    alert(
        `Request ID: ${data.requestId}\n` +
        `Decision: ${result.isDeepfake ? "Deepfake suspected" : "Normal"}\n` +
        `Confidence: ${confidence}%\n` +
        `Face count: ${result.faceCount}\n` +
        `Watermark detected: ${result.watermarkDetected ? "Yes" : "No"}\n` +
        `Model version: ${result.modelVersion}\n` +
        `Processing time: ${result.processingTimeMs}ms\n` +
        `Message: ${result.message}` +
        buildFaceSummary(faces)
    );
}

const observer = new MutationObserver(() => {
    scheduleAttachButtons();
});

if (document.body) {
    observer.observe(document.body, {
        childList: true,
        subtree: true,
    });
}

window.addEventListener("scroll", scheduleAttachButtons, { passive: true });
window.addEventListener("resize", scheduleAttachButtons, { passive: true });

scheduleAttachButtons();
