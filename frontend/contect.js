// extension/content.js 또는 popup.js
async function checkDeepfake(base64Image) {
    const apiEndpoint = "http://localhost:8080/api/analyze";
    
    const requestData = {
        imageId: "img_" + Date.now(),
        base64Data: base64Image // 실제로는 전처리된 데이터
    };

    
    try {
        console.log("분석 요청 중...");
        const response = await fetch(apiEndpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(requestData)
        });

        const result = await response.json();
        
        if (result.is_deepfake) {
            alert(`경고! 딥페이크 확률: ${result.probability * 100}%`);
        } else {
            console.log("정상 미디어입니다.");
        }
    } catch (error) {
        console.error("통신 오류 발생:", error);
    }
}

// 테스트를 위한 더미 데이터 실행
// checkDeepfake("data:image/png;base64,iVBORw0KGgoAAAANSUhEUg...");