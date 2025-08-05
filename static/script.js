let userLocation = "";

// ========== Get Location ==========
if (navigator.geolocation) {
  navigator.geolocation.getCurrentPosition(
    (position) => {
      userLocation = `${position.coords.latitude},${position.coords.longitude}`;
    },
    () => {
      alert("Location access denied. Please enable it for better results.");
    }
  );
} else {
  alert("Geolocation is not supported by this browser.");
}

// ========== Handle Text Input Submit ==========
async function send() {
  const message = document.getElementById("input").value;
  const responseBox = document.getElementById("response");
  const confirmBtn = document.getElementById("confirm-btn");

  const res = await fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      location: userLocation,
    }),
  });

  const data = await res.json();
  responseBox.innerText = `Response: ${data.response}`;

  if (data.response && data.response.toLowerCase().includes("tentatively booked")) {
    confirmBtn.style.display = "inline-block"; // Show confirmation button
  } else {
    confirmBtn.style.display = "none";
  }
}

// ========== Handle Confirmation ==========
async function confirmAppointment() {
  const responseBox = document.getElementById("response");
  const confirmBtn = document.getElementById("confirm-btn");

  const res = await fetch("/api/confirm", {
    method: "POST",
  });

  const data = await res.json();
  responseBox.innerText = `✅ ${data.response || data.error}`;
  confirmBtn.style.display = "none"; // Hide after confirmation
}

// ========== Voice Input Handler ==========
function startVoice() {
  const recognition = new webkitSpeechRecognition();
  recognition.lang = "en-US";
  recognition.onresult = function (event) {
    document.getElementById("input").value = event.results[0][0].transcript;
  };
  recognition.start();
}
