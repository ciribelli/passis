import app


@app.route('/threads', methods=['GET'])
def get_threads():
    if request.method == 'GET':
        threads = Thread.query.order_by(Thread.date_created.desc()).limit(6).all()
        serialized_threads = [thread.content for thread in threads]
        return serialized_threads, 200


        

def thread_app():
    threads = Thread.query.with_entities(Thread.content).order_by(Thread.date_created.desc()).limit(4).all()
    return threads

print(thread_app)

