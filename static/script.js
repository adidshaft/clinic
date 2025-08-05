let userLocation = "";
let pendingAppointment = null;

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

  if (data.confirmation_needed && data.appointment) {
    pendingAppointment = data.appointment;
    document.getElementById("confirmationButtons").style.display = "block";
  } else {
    pendingAppointment = null;
    document.getElementById("confirmationButtons").style.display = "none";
  }
}

async function confirmAppointment() {
  if (!pendingAppointment) return;

  const res = await fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      confirm: true,
      appointment: pendingAppointment
    })
  });

  const data = await res.json();
  document.getElementById("response").innerText = data.response;

  pendingAppointment = null;
  document.getElementById("confirmationButtons").style.display = "none";
}

function cancelAppointment() {
  document.getElementById("response").innerText = "❌ Okay, appointment not booked.";
  pendingAppointment = null;
  document.getElementById("confirmationButtons").style.display = "none";
}

function startVoice() {
  const recognition = new webkitSpeechRecognition();
  recognition.lang = "en-US";
  recognition.onresult = function (event) {
    document.getElementById("input").value = event.results[0][0].transcript;
  };
  recognition.start();
}
