$(document).ready(function(){
    $("button").click(function(){
      var value = $(this).val();
      console.log(value);
      $.post('./change',
            { 'value': value })
      setTimeout(() => {window.location.href = '/'},500)   
    });
  });