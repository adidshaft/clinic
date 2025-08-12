let userLocation = "";
let pendingAppointment = null;

// Global variables for the enhanced booking system
let currentStep = 1;
let appointmentData = {
  healthConcern: '',
  appointmentTime: '',
  patientInfo: {},
  location: ''
};

// Initialize location tracking
if (navigator.geolocation) {
  navigator.geolocation.getCurrentPosition((position) => {
    userLocation = `Latitude: ${position.coords.latitude}, Longitude: ${position.coords.longitude}`;
    console.log('Location detected:', userLocation);
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
    if ((responseText.includes('available') && responseText.includes('would you like to book')) ||
        (responseText.includes('✅') && responseText.includes('available at'))) {
      
      // Extract appointment time from response
      const timeMatch = data.response.match(/available at ([^.?!]+)/i);
      if (timeMatch) {
        pendingAppointment = {
          time: timeMatch[1].trim(),
          reason: message,
          location: userLocation
        };
        
        // Store data for enhanced booking system
        appointmentData.healthConcern = message;
        appointmentData.appointmentTime = timeMatch[1].trim();
        appointmentData.location = userLocation;
        
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
    bookingButtons.style.display = "flex";
    console.log('Booking buttons shown');
  }
}

function hideBookingButtons() {
  const bookingButtons = document.getElementById("booking-buttons");
  if (bookingButtons) {
    bookingButtons.style.display = "none";
    console.log('Booking buttons hidden');
  }
}

// Step navigation functions
function showStep(stepNumber) {
  // Hide all steps
  document.querySelectorAll('.form-step').forEach(step => {
    step.classList.remove('active');
  });
  
  // Show target step
  const targetStep = document.getElementById(`step${stepNumber}`);
  if (targetStep) {
    targetStep.classList.add('active');
    currentStep = stepNumber;
    console.log('Showing step:', stepNumber);
  }
}

function goBackToStep1() {
  showStep(1);
}

function goBackToStep2() {
  showStep(2);
}

function showPatientForm() {
  console.log('showPatientForm called');
  
  // Store the appointment data from the initial interaction
  appointmentData.healthConcern = document.getElementById("input").value;
  appointmentData.location = userLocation || '';
  
  // Extract appointment time from the AI response
  const responseText = document.getElementById("response").innerText;
  const timeMatch = responseText.match(/available at ([^.?!]+)/i);
  if (timeMatch) {
    appointmentData.appointmentTime = timeMatch[1].trim();
  }
  
  console.log('Appointment data:', appointmentData);
  
  // Hide booking buttons and show patient form
  hideBookingButtons();
  showStep(2);
}

function cancelBooking() {
  console.log('cancelBooking called');
  document.getElementById("response").innerText = `❌ Booking Cancelled. Feel free to ask about other available times.`;
  hideBookingButtons();
  pendingAppointment = null;
}

async function confirmAppointment() {
  console.log('confirmAppointment called, currentStep:', currentStep);
  
  // Check if we're in Step 3 (final confirmation)
  if (currentStep === 3) {
    const confirmButton = event.target;
    confirmButton.disabled = true;
    confirmButton.textContent = 'Booking...';

    try {
      const response = await fetch('/api/book-appointment', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(appointmentData)
      });

      const result = await response.json();
      
      if (result.success) {
        document.getElementById('confirmationMessage').innerHTML = `
          <strong>Dr. Lee</strong> will see you at <strong>${appointmentData.appointmentTime}</strong><br>
          <strong>Confirmation ID:</strong> ${result.confirmationId}<br><br>
          Please arrive 15 minutes early and bring a valid ID.
        `;
        showStep(4);
      } else {
        alert('Booking failed: ' + result.error);
        confirmButton.disabled = false;
        confirmButton.textContent = '✅ Confirm Appointment';
      }
    } catch (error) {
      alert('Network error. Please try again.');
      confirmButton.disabled = false;
      confirmButton.textContent = '✅ Confirm Appointment';
    }
  } else if (!pendingAppointment) {
    alert('No pending appointment to confirm.');
    return;
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

function startNewBooking() {
  // Reset form and data
  appointmentData = {
    healthConcern: '',
    appointmentTime: '',
    patientInfo: {},
    location: ''
  };
  
  const inputElement = document.getElementById('input');
  const responseElement = document.getElementById('response');
  const formElement = document.getElementById('patientForm');
  
  if (inputElement) inputElement.value = '';
  if (responseElement) responseElement.textContent = 'Your response will appear here...';
  if (formElement) formElement.reset();
  
  clearAllErrors();
  showStep(1);
}

// Form validation functions
function validateEmail(email) {
  const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return re.test(email);
}

function validatePhone(phone) {
  const re = /^[\+]?[1-9][\d]{0,15}$/;
  return re.test(phone.replace(/[\s\-\(\)]/g, ''));
}

function showError(fieldId, message) {
  const errorElement = document.getElementById(fieldId + 'Error');
  if (errorElement) {
    errorElement.textContent = message;
  }
}

function clearError(fieldId) {
  const errorElement = document.getElementById(fieldId + 'Error');
  if (errorElement) {
    errorElement.textContent = '';
  }
}

function clearAllErrors() {
  ['firstName', 'lastName', 'age', 'gender', 'email', 'phone'].forEach(clearError);
}

function validateAndProceed() {
  console.log('validateAndProceed called');
  clearAllErrors();
  let isValid = true;

  // Get form values
  const firstName = document.getElementById('firstName').value.trim();
  const lastName = document.getElementById('lastName').value.trim();
  const age = document.getElementById('age').value;
  const gender = document.getElementById('gender').value;
  const email = document.getElementById('email').value.trim();
  const phone = document.getElementById('phone').value.trim();

  // Validate required fields
  if (!firstName) {
    showError('firstName', 'First name is required');
    isValid = false;
  }

  if (!lastName) {
    showError('lastName', 'Last name is required');
    isValid = false;
  }

  if (!age || age < 1 || age > 120) {
    showError('age', 'Please enter a valid age (1-120)');
    isValid = false;
  }

  if (!gender) {
    showError('gender', 'Please select your gender');
    isValid = false;
  }

  if (!email) {
    showError('email', 'Email address is required');
    isValid = false;
  } else if (!validateEmail(email)) {
    showError('email', 'Please enter a valid email address');
    isValid = false;
  }

  if (!phone) {
    showError('phone', 'Phone number is required');
    isValid = false;
  } else if (!validatePhone(phone)) {
    showError('phone', 'Please enter a valid phone number');
    isValid = false;
  }

  if (isValid) {
    // Save patient info
    appointmentData.patientInfo = {
      firstName,
      lastName,
      age: parseInt(age),
      gender,
      email,
      phone,
      medicalId: document.getElementById('medicalId').value.trim(),
      emergencyContact: document.getElementById('emergencyContact').value.trim(),
      emergencyPhone: document.getElementById('emergencyPhone').value.trim(),
      allergies: document.getElementById('allergies').value.trim()
    };

    console.log('Patient info saved:', appointmentData.patientInfo);
    showAppointmentSummary();
    showStep(3);
  }
}

function showAppointmentSummary() {
  const summary = document.getElementById('appointmentSummary');
  if (!summary) return;
  
  const patient = appointmentData.patientInfo;
  
  summary.innerHTML = `
    <h3 style="margin-top: 0; color: var(--primary-color);">Appointment Details</h3>
    <div class="summary-item">
      <span><strong>Patient:</strong></span>
      <span>${patient.firstName} ${patient.lastName}</span>
    </div>
    <div class="summary-item">
      <span><strong>Age:</strong></span>
      <span>${patient.age} years old</span>
    </div>
    <div class="summary-item">
      <span><strong>Gender:</strong></span>
      <span>${patient.gender.charAt(0).toUpperCase() + patient.gender.slice(1)}</span>
    </div>
    <div class="summary-item">
      <span><strong>Email:</strong></span>
      <span>${patient.email}</span>
    </div>
    <div class="summary-item">
      <span><strong>Phone:</strong></span>
      <span>${patient.phone}</span>
    </div>
    ${patient.medicalId ? `
    <div class="summary-item">
      <span><strong>Medical ID:</strong></span>
      <span>${patient.medicalId}</span>
    </div>
    ` : ''}
    <div class="summary-item">
      <span><strong>Appointment Time:</strong></span>
      <span>${appointmentData.appointmentTime}</span>
    </div>
    <div class="summary-item">
      <span><strong>Health Concern:</strong></span>
      <span>${appointmentData.healthConcern}</span>
    </div>
    ${patient.allergies ? `
    <div class="summary-item">
      <span><strong>Allergies:</strong></span>
      <span>${patient.allergies}</span>
    </div>
    ` : ''}
  `;
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

// Enhanced location display
function updateLocationDisplay() {
  const locationElement = document.getElementById('location-text');
  if (!locationElement) return;
  
  if (navigator.geolocation) {
    locationElement.textContent = "📍 Getting your location...";
    
    navigator.geolocation.getCurrentPosition(async (position) => {
      try {
        locationElement.textContent = "📍 Getting location name...";
        
        const response = await fetch(`https://api.bigdatacloud.net/data/reverse-geocode-client?latitude=${position.coords.latitude}&longitude=${position.coords.longitude}&localityLanguage=en`);
        const data = await response.json();
        const cityName = data.city || data.locality || data.principalSubdivision || "Unknown Location";
        
        locationElement.textContent = `📍 Location: ${cityName}`;
        appointmentData.location = cityName;
        
      } catch (error) {
        locationElement.textContent = `📍 Location detected (coordinates available)`;
      }
    }, (error) => {
      locationElement.textContent = `📍 Location access denied. Please enable location for better service.`;
    });
  } else {
    locationElement.textContent = `📍 Geolocation is not supported by this browser.`;
  }
}

// Simple theme toggle functionality
function toggleTheme() {
  const currentTheme = document.documentElement.getAttribute('data-theme');
  const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', newTheme);
  localStorage.setItem('theme', newTheme);
  
  const button = document.querySelector('.theme-toggle');
  if (button) {
    button.textContent = newTheme === 'dark' ? '☀️' : '🌙';
  }
}

// Initialize everything on page load
document.addEventListener('DOMContentLoaded', function() {
  console.log('DOM loaded, initializing...');
  
  // Set theme
  const savedTheme = localStorage.getItem('theme') || 'light';
  document.documentElement.setAttribute('data-theme', savedTheme);
  const button = document.querySelector('.theme-toggle');
  if (button) {
    button.textContent = savedTheme === 'dark' ? '☀️' : '🌙';
  }
  
  // Initialize location display
  updateLocationDisplay();
  
  console.log('Initialization complete');
});