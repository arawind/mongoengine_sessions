#MongoEngine Sessions

Sessions in MongoDB using MongoEngine for Pyramid (quite narrow, innit?)

Code borrowed from [pyramid_redis_sessions] 

No pypi support, clone and import mongoengine_session. In pyramid's __init__'s `main` function, add `config.include('mongoengine_sessions')` 

And in your .ini file, under `[app:main]` add `mongoengine_sessions.secret = 'yoursecrethere'` line

[pyramid_redis_sessions]:https://github.com/ericrasmussen/pyramid_redis_sessions
