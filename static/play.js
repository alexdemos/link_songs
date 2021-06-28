$(document).ready(function(){
    $("#stop").click(function()
    {
      $.post('/play_songs', 
            { 'stop': 'stop' })    
    });
  });