console.log("🛡️ VeritAI 스크립트 로드됨");

let isProcessing = false;
const processedMedia = new WeakSet();

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
    if (!parent) return null;

    const style = window.getComputedStyle(parent);
    if (style.position === "static") {
        parent.style.position = "relative";
    }

    return parent;
}

function createButton(media) {
    const btn = document.createElement("button");
    btn.innerText = "🔍 검사";
    btn.className = "veritai-check-btn";
    btn.style.cssText = `
        position: absolute;
        top: 10px;
        left: 10px;
        z-index: 2147483647;
        padding: 6px 10px;
        background-color: #e74c3c;
        color: white;
        border: 2px solid white;
        border-radius: 6px;
        cursor: pointer;
        font-weight: bold;
        font-size: 13px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.3);
    `;

    btn.addEventListener("click", async (e) => {
        e.preventDefault();
        e.stopPropagation();

        if (isProcessing) {
            alert("이미 처리 중입니다.");
            return;
        }

        isProcessing = true;
        btn.innerText = "⏳ 처리 중";
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
            console.error("미디어 처리 오류:", error);

            const message = error?.message || String(error);
            if (message.includes("Extension context invalidated")) {
                alert("확장 프로그램이 갱신되어 연결이 끊어졌습니다. 페이지를 새로고침한 뒤 다시 시도하세요.");
            } else {
                alert(`오류: ${message}`);
            }
        } finally {
            btn.innerText = "🔍 검사";
            btn.disabled = false;
            isProcessing = false;
        }
    });

    return btn;
}

function attachButtons() {
    const mediaList = document.querySelectorAll("video, img");

    mediaList.forEach((media) => {
        if (!media.isConnected) return;
        if (!(media instanceof HTMLImageElement || media instanceof HTMLVideoElement)) return;

        const wrapper = ensureWrapper(media);
        if (!wrapper) return;

        // 너무 작거나 안 보이는 건 스킵
        if (!isVisibleMedia(media)) return;

        // 이미 붙어 있으면 중복 방지
        const existingBtn = wrapper.querySelector(":scope > .veritai-check-btn");
        if (existingBtn) return;

        // 이미지가 아직 실제 로딩되지 않았으면 스킵
        if (media.tagName === "IMG") {
            const img = media;
            if (!img.currentSrc && !img.src) return;
        }

        const btn = createButton(media);
        wrapper.appendChild(btn);
        processedMedia.add(media);
    });
}

async function captureVideoBlob(video) {
    if (!video) {
        throw new Error("비디오 요소를 찾을 수 없습니다.");
    }

    const rect = video.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) {
        throw new Error("비디오 크기가 0입니다.");
    }

    return new Promise((resolve, reject) => {
        chrome.runtime.sendMessage({ action: "capture_tab" }, (res) => {
            if (chrome.runtime.lastError) {
                reject(new Error(chrome.runtime.lastError.message));
                return;
            }

            if (!res || res.error || !res.dataUrl) {
                reject(new Error(res?.error || "캡처 데이터가 없습니다."));
                return;
            }

            const fullImage = new Image();

            fullImage.onload = () => {
                try {
                    const canvas = document.createElement("canvas");
                    const ctx = canvas.getContext("2d");
                    if (!ctx) {
                        reject(new Error("캔버스 생성 실패"));
                        return;
                    }

                    const dpr = window.devicePixelRatio || 1;
                    const scrollX = window.scrollX;
                    const scrollY = window.scrollY;

                    canvas.width = Math.floor(rect.width * dpr);
                    canvas.height = Math.floor(rect.height * dpr);

                    ctx.drawImage(
                        fullImage,
                        Math.floor((rect.left + scrollX) * dpr),
                        Math.floor((rect.top + scrollY) * dpr),
                        Math.floor(rect.width * dpr),
                        Math.floor(rect.height * dpr),
                        0,
                        0,
                        canvas.width,
                        canvas.height
                    );

                    canvas.toBlob((blob) => {
                        if (!blob) {
                            reject(new Error("비디오 Blob 생성 실패"));
                            return;
                        }
                        resolve(blob);
                    }, "image/jpeg", 0.9);
                } catch (err) {
                    reject(err);
                }
            };

            fullImage.onerror = () => reject(new Error("캡처 이미지 로드 실패"));
            fullImage.src = res.dataUrl;
        });
    });
}

async function captureImageBlob(url) {
    if (!url) {
        throw new Error("이미지 URL이 없습니다.");
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
                    reject(new Error("캔버스 생성 실패"));
                    return;
                }

                canvas.width = img.naturalWidth || img.width;
                canvas.height = img.naturalHeight || img.height;

                if (canvas.width === 0 || canvas.height === 0) {
                    reject(new Error("이미지 크기가 0입니다."));
                    return;
                }

                ctx.drawImage(img, 0, 0);

                canvas.toBlob((blob) => {
                    if (!blob) {
                        reject(new Error("이미지 Blob 생성 실패"));
                        return;
                    }
                    resolve(blob);
                }, "image/jpeg", 0.9);
            } catch (err) {
                reject(err);
            }
        };

        img.onerror = () => reject(new Error("이미지 로드 실패"));
        img.src = url;
    });
}

async function sendToBackend(blob, mediaType) {
    const formData = new FormData();
    formData.append("file", blob, "capture.jpg");
    formData.append("sourceUrl", window.location.href);
    formData.append("mediaType", mediaType);
    formData.append("clientType", "chrome-extension");

    const response = await fetch("http://localhost:8080/api/detections", {
        method: "POST",
        body: formData
    });

    if (!response.ok) {
        const text = await response.text();
        throw new Error(`서버 응답 오류: ${response.status} / ${text}`);
    }

    const data = await response.json();
    if (data.status !== "DONE") {
        throw new Error(data.message || "분석이 정상 완료되지 않았습니다.");
    }

    const result = data.result;
    const prob = (result.confidence * 100).toFixed(2);

    alert(
        `요청 ID: ${data.requestId}\n` +
        `판정: ${result.isDeepfake ? "딥페이크 의심" : "정상"}\n` +
        `신뢰도: ${prob}%\n` +
        `얼굴 수: ${result.faceCount}\n` +
        `워터마크 탐지: ${result.watermarkDetected ? "예" : "아니오"}\n` +
        `모델 버전: ${result.modelVersion}\n` +
        `처리 시간: ${result.processingTimeMs}ms\n` +
        `메시지: ${result.message}`
    );
}

attachButtons();

const observer = new MutationObserver(() => {
    attachButtons();
});

observer.observe(document.body, {
    childList: true,
    subtree: true,
    attributes: true
});

window.addEventListener("scroll", attachButtons, { passive: true });
window.addEventListener("resize", attachButtons);