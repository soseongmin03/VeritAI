chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "capture_tab") {
        chrome.tabs.captureVisibleTab(
            null,
            { format: "jpeg", quality: 90 },
            (dataUrl) => {
                if (chrome.runtime.lastError) {
                    sendResponse({ error: chrome.runtime.lastError.message });
                    return;
                }
                if (!dataUrl) {
                    sendResponse({ error: "캡처된 데이터가 없습니다." });
                    return;
                }
                sendResponse({ dataUrl });
            }
        );
        return true;
    }

    // 이미지 CORS(보안) 우회용
    if (request.action === "fetch_image") {
        fetch(request.url, { mode: 'cors' })
            .then(res => res.blob())
            .then(blob => {
                const reader = new FileReader();
                reader.onloadend = () => sendResponse({ dataUrl: reader.result });
                reader.readAsDataURL(blob);
            })
            .catch(err => {
                sendResponse({ error: "CORS fetch 실패: " + err.message });
            });
        return true;
    }
    sendResponse({ error: "알 수 없는 요청입니다." });
});