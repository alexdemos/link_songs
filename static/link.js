$(document).ready(function(){
    $("div > button").click(function(){
      var value = $(this).val();
      $.post('./link',
            { 'value': value }) 
      setTimeout(() => {window.location.href = '/'},10)    
    });
  });

  