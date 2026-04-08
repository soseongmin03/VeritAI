chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "capture_tab") {
        chrome.tabs.captureVisibleTab(
            null,
            { format: "jpeg", quality: 90 },
            (dataUrl) => {
                if (chrome.runtime.lastError) {
                    console.error("captureVisibleTab 오류:", chrome.runtime.lastError.message);
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

    sendResponse({ error: "알 수 없는 요청입니다." });
});