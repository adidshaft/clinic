let userLocation = "";

if (navigator.geolocation) {
  navigator.geolocation.getCurrentPosition((position) => {
    userLocation = `Latitude: ${position.coords.latitude}, Longitude: ${position.coords.longitude}`;
  }, () => {
    alert("Location access denied. Please enable it for better results.");
  });
} else {
  alert("Geolocation is not supported by this browser.");
}


async function send() {
  const message = document.getElementById("input").value;
  const res = await fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      location: userLocation
    })
  });
  const data = await res.json();
  document.getElementById("response").innerText = data.response;
}

  
  function startVoice() {
    const recognition = new webkitSpeechRecognition();
    recognition.lang = "en-US";
    recognition.onresult = function (event) {
      document.getElementById("input").value = event.results[0][0].transcript;
    };
    recognition.start();
  }
  