window.addEventListener("load", function () {
  const signOutButton = document.getElementById("sign-out");
  if (signOutButton) {
    signOutButton.onclick = function () {
      firebase.auth().signOut();
    };
  }

  var uiConfig = {
    signInFlow: "popup",
    signInSuccessUrl: "/",
    signInOptions: [
      firebase.auth.GoogleAuthProvider.PROVIDER_ID,
      firebase.auth.EmailAuthProvider.PROVIDER_ID,
    ],
    tosUrl: "/",
  };

  firebase.auth().onAuthStateChanged(
    function (user) {
      if (user) {
        if (signOutButton) signOutButton.hidden = false;
        var loginInfo = document.getElementById("login-info");
        if (loginInfo) loginInfo.hidden = false;
        user.getIdToken().then(function (token) {
          document.cookie = "token=" + token;
        });
      } else {
        var ui = new firebaseui.auth.AuthUI(firebase.auth());
        ui.start("#firebaseui-auth-container", uiConfig);
        if (signOutButton) signOutButton.hidden = true;
        var loginInfo = document.getElementById("login-info");
        if (loginInfo) loginInfo.hidden = true;
        document.cookie = "token=";
      }
    },
    function (error) {
      console.error(error);
      alert("Unable to log in: " + error);
    }
  );
});
