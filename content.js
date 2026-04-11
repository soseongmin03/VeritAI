console.log("VeritAI content script loaded");

const API_URL = "http://localhost:8080/api/detections";
const BUTTON_CLASS = "veritai-check-btn";
const BUTTON_IDLE_LABEL = "\uac80\uc0ac";
const BUTTON_BUSY_LABEL = "\ubd84\uc11d\uc911";

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
    btn.title = "VeritAI \uac80\uc0ac";
    btn.setAttribute("aria-label", "VeritAI \uac80\uc0ac");
    btn.style.cssText = `
        position: absolute;
        top: 10px;
        left: 10px;
        z-index: 2147483647;
        width: 48px;
        height: 38px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        padding: 0 6px;
        background-color: #e74c3c;
        color: white;
        border: 2px solid white;
        border-radius: 999px;
        cursor: pointer;
        font-weight: bold;
        font-size: 12px;
        box-shadow: 0 2px 5px rgba(0, 0, 0, 0.3);
    `;

    btn.addEventListener("click", async (event) => {
        event.preventDefault();
        event.stopPropagation();

        if (isProcessing) {
            alert("\ub2e4\ub978 \uac80\uc0ac\uac00 \uc774\ubbf8 \uc9c4\ud589 \uc911\uc785\ub2c8\ub2e4.");
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
                alert("\ud655\uc7a5 \ud504\ub85c\uadf8\ub7a8\uc774 \ub2e4\uc2dc \ub85c\ub4dc\ub418\uc5c8\uc2b5\ub2c8\ub2e4. \ud398\uc774\uc9c0\ub97c \uc0c8\ub85c\uace0\uce68\ud55c \ub4a4 \ub2e4\uc2dc \uc2dc\ub3c4\ud574\uc8fc\uc138\uc694.");
            } else {
                alert(`\uc624\ub958: ${message}`);
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
        throw new Error("\uc601\uc0c1 \uc694\uc18c\ub97c \ucc3e\uc744 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4.");
    }

    const rect = video.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) {
        throw new Error("\uc601\uc0c1 \ud06c\uae30\uac00 0\uc785\ub2c8\ub2e4.");
    }

    return new Promise((resolve, reject) => {
        chrome.runtime.sendMessage({ action: "capture_tab" }, (response) => {
            if (chrome.runtime.lastError) {
                reject(new Error(chrome.runtime.lastError.message));
                return;
            }
            if (!response || response.error || !response.dataUrl) {
                reject(new Error(response?.error || "\ucea1\ucc98 \ub370\uc774\ud130\ub97c \ubc1b\uc544\uc624\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4."));
                return;
            }

            const fullImage = new Image();
            fullImage.onload = () => {
                try {
                    const canvas = document.createElement("canvas");
                    const ctx = canvas.getContext("2d");
                    if (!ctx) {
                        reject(new Error("\uce94\ubc84\uc2a4 \ucee8\ud14d\uc2a4\ud2b8\ub97c \uc0dd\uc131\ud558\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4."));
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
                            reject(new Error("\uc601\uc0c1 \ud504\ub808\uc784 \ub370\uc774\ud130\ub97c \uc0dd\uc131\ud558\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4."));
                            return;
                        }
                        resolve(blob);
                    }, "image/jpeg", 0.9);
                } catch (error) {
                    reject(error);
                }
            };
            fullImage.onerror = () => reject(new Error("\ucea1\ucc98\ud55c \ud0ed \uc774\ubbf8\uc9c0\ub97c \ubd88\ub7ec\uc624\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4."));
            fullImage.src = response.dataUrl;
        });
    });
}

async function captureImageBlob(url) {
    if (!url) {
        throw new Error("\uc774\ubbf8\uc9c0 \uc8fc\uc18c\uac00 \uc5c6\uc2b5\ub2c8\ub2e4.");
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
                    reject(new Error("\uce94\ubc84\uc2a4 \ucee8\ud14d\uc2a4\ud2b8\ub97c \uc0dd\uc131\ud558\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4."));
                    return;
                }

                canvas.width = img.naturalWidth || img.width;
                canvas.height = img.naturalHeight || img.height;

                if (canvas.width === 0 || canvas.height === 0) {
                    reject(new Error("\uc774\ubbf8\uc9c0 \ud06c\uae30\uac00 0\uc785\ub2c8\ub2e4."));
                    return;
                }

                ctx.drawImage(img, 0, 0);
                canvas.toBlob((blob) => {
                    if (!blob) {
                        reject(new Error("\uc774\ubbf8\uc9c0 \ub370\uc774\ud130\ub97c \uc0dd\uc131\ud558\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4."));
                        return;
                    }
                    resolve(blob);
                }, "image/jpeg", 0.9);
            } catch (error) {
                reject(error);
            }
        };

        img.onerror = () => reject(new Error("\uc774\ubbf8\uc9c0\ub97c \ubd88\ub7ec\uc624\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4."));
        img.src = url;
    });
}

function buildFaceSummary(faces) {
    if (!faces.length) {
        return "\n\n\uac10\uc9c0\ub41c \uc5bc\uad74\uc774 \uc5c6\uc2b5\ub2c8\ub2e4. \uc5bc\uad74\uc774 \ub354 \ud06c\uac70\ub098 \uc120\uba85\ud55c \uc774\ubbf8\uc9c0\ub97c \uc0ac\uc6a9\ud574\ubcf4\uc138\uc694.";
    }

    return "\n\n" + faces.slice(0, 3).map((face, index) => {
        const bbox = face?.bbox || {};
        const quality = face?.quality || {};
        const detectionConfidence = (face?.detectionConfidence ?? face?.score ?? 0) * 100;
        const qualityScore = (quality?.score ?? 0) * 100;

        return [
            `[\uc5bc\uad74 ${index + 1}]`,
            `\uc704\uce58: (${bbox.x ?? "?"}, ${bbox.y ?? "?"}, ${bbox.w ?? "?"}x${bbox.h ?? "?"})`,
            `\uc720\ud615: ${face?.faceMode || "\uc54c \uc218 \uc5c6\uc74c"}`,
            `\uac80\ucd9c \uc2e0\ub8b0\ub3c4: ${detectionConfidence.toFixed(1)}%`,
            `\ud488\uc9c8: ${quality?.label || "\uc54c \uc218 \uc5c6\uc74c"} (${qualityScore.toFixed(1)}%)`,
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
        throw new Error(`\uc11c\ubc84 \uc751\ub2f5 \uc624\ub958: ${response.status} / ${await response.text()}`);
    }

    const data = await response.json();
    if (!data || data.status !== "DONE" || !data.result) {
        throw new Error(data?.message || "\ubd84\uc11d\uc774 \uc815\uc0c1\uc801\uc73c\ub85c \uc644\ub8cc\ub418\uc9c0 \uc54a\uc558\uc2b5\ub2c8\ub2e4.");
    }

    const result = data.result;
    const confidence = ((result.confidence || 0) * 100).toFixed(2);
    const faces = Array.isArray(result.faces) ? result.faces : [];

    alert(
        `\uc694\uccad ID: ${data.requestId}\n` +
        `\ud310\uc815 \uacb0\uacfc: ${result.isDeepfake ? "\ub515\ud398\uc774\ud06c \uc758\uc2ec" : "\uc815\uc0c1"}\n` +
        `\uc2e0\ub8b0\ub3c4: ${confidence}%\n` +
        `\uac10\uc9c0\ub41c \uc5bc\uad74 \uc218: ${result.faceCount}\n` +
        `\uc6cc\ud130\ub9c8\ud06c \uac10\uc9c0: ${result.watermarkDetected ? "\uc608" : "\uc544\ub2c8\uc624"}\n` +
        `\ubaa8\ub378 \ubc84\uc804: ${result.modelVersion}\n` +
        `\ucc98\ub9ac \uc2dc\uac04: ${result.processingTimeMs}ms\n` +
        `\ubd84\uc11d \uba54\uc2dc\uc9c0: ${result.message}` +
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
