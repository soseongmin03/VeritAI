chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action !== "capture_tab") {
        sendResponse({ error: "Unsupported request." });
        return;
    }

    chrome.tabs.captureVisibleTab(
        null,
        { format: "jpeg", quality: 90 },
        (dataUrl) => {
            if (chrome.runtime.lastError) {
                console.error("captureVisibleTab error:", chrome.runtime.lastError.message);
                sendResponse({ error: chrome.runtime.lastError.message });
                return;
            }

            if (!dataUrl) {
                sendResponse({ error: "No captured image data returned." });
                return;
            }

            sendResponse({ dataUrl });
        }
    );

    return true;
});
