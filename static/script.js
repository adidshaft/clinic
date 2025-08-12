let userLocation = "";
let pendingAppointment = null;

if (navigator.geolocation) {
  navigator.geolocation.getCurrentPosition((position) => {
    userLocation = `Latitude: ${position.coords.latitude}, Longitude: ${position.coords.longitude}`;
  }, () => {
    console.log("Location access denied. Please enable it for better results.");
  });
} else {
  console.log("Geolocation is not supported by this browser.");
}

async function send() {
  const message = document.getElementById("input").value;
  
  if (!message.trim()) {
    alert('Please enter your health concern first.');
    return;
  }

  // Show loading state
  document.getElementById("response").innerText = "Processing your request...";
  
  try {
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

    // Check if the response indicates an available appointment slot
    const responseText = data.response.toLowerCase();
    
    // Look for patterns that indicate appointment availability
    if (responseText.includes('available') && 
        responseText.includes('would you like to book') ||
        (responseText.includes('✅') && responseText.includes('available at'))) {
      
      // Extract appointment time from response
      const timeMatch = data.response.match(/available at ([^.?!]+)/i);
      if (timeMatch) {
        pendingAppointment = {
          time: timeMatch[1].trim(),
          reason: message,
          location: userLocation
        };
        
        // Show booking buttons
        showBookingButtons();
      }
    } else {
      // Hide booking buttons if not an available appointment
      hideBookingButtons();
    }
    
  } catch (error) {
    document.getElementById("response").innerText = "Error: Unable to process your request. Please try again.";
    hideBookingButtons();
  }
}

function showBookingButtons() {
  const bookingButtons = document.getElementById("booking-buttons");
  if (bookingButtons) {
    bookingButtons.style.display = "block";
  }
}

function hideBookingButtons() {
  const bookingButtons = document.getElementById("booking-buttons");
  if (bookingButtons) {
    bookingButtons.style.display = "none";
  }
}

async function confirmAppointment() {
  if (!pendingAppointment) {
    alert('No pending appointment to confirm.');
    return;
  }

  // This function is handled by the enhanced booking system in index.html
  // It will trigger the patient information form
  if (typeof showPatientForm === 'function') {
    // Store appointment data globally for the enhanced booking system
    if (typeof appointmentData !== 'undefined') {
      appointmentData.healthConcern = pendingAppointment.reason;
      appointmentData.appointmentTime = pendingAppointment.time;
      appointmentData.location = pendingAppointment.location;
    }
    showPatientForm();
  } else {
    // Fallback for basic booking without patient form
    try {
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
      hideBookingButtons();
      pendingAppointment = null;
    } catch (error) {
      alert('Error confirming appointment. Please try again.');
    }
  }
}

function cancelAppointment() {
  document.getElementById("response").innerText = "❌ Okay, appointment not booked. Feel free to ask about other available times.";
  hideBookingButtons();
  pendingAppointment = null;
}

function startVoice() {
  if (!('webkitSpeechRecognition' in window)) {
    alert('Speech recognition not supported in this browser. Try Chrome or Edge.');
    return;
  }

  const recognition = new webkitSpeechRecognition();
  recognition.lang = "en-US";
  recognition.onresult = function (event) {
    document.getElementById("input").value = event.results[0][0].transcript;
  };
  recognition.onerror = function() {
    alert('Speech recognition failed. Please try again.');
  };
  recognition.start();
}